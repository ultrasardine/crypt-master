"""Bot management views."""

from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DetailView, ListView, View

from apps.core.models import TradingPair

from .models import Bot, BotEvent, BotStatus, BotType


class BotListView(ListView):
    """List view for bots with filtering."""

    model = Bot
    template_name = "bots/bot_list.html"
    context_object_name = "bots"
    paginate_by = 20

    def get_queryset(self):
        """Filter bots based on query parameters."""
        queryset = Bot.objects.select_related("trading_pair").all()

        # Filter by status
        status = self.request.GET.get("status")
        if status and status in dict(BotStatus.choices):
            queryset = queryset.filter(status=status)

        # Filter by bot type
        bot_type = self.request.GET.get("type")
        if bot_type and bot_type in dict(BotType.choices):
            queryset = queryset.filter(bot_type=bot_type)

        # Filter by mode (simulated/live)
        mode = self.request.GET.get("mode")
        if mode == "simulated":
            queryset = queryset.simulated()
        elif mode == "live":
            queryset = queryset.live()

        # Filter by trading pair
        symbol = self.request.GET.get("symbol")
        if symbol:
            queryset = queryset.for_pair(symbol)

        return queryset

    def get_context_data(self, **kwargs):
        """Add filter options and summary stats to context."""
        context = super().get_context_data(**kwargs)

        # Filter options
        context["status_choices"] = BotStatus.choices
        context["type_choices"] = BotType.choices
        context["trading_pairs"] = TradingPair.objects.active()

        # Current filter values
        context["current_status"] = self.request.GET.get("status", "")
        context["current_type"] = self.request.GET.get("type", "")
        context["current_mode"] = self.request.GET.get("mode", "")
        context["current_symbol"] = self.request.GET.get("symbol", "")

        # Summary statistics
        all_bots = Bot.objects.all()
        context["total_bots"] = all_bots.count()
        context["active_bots_count"] = all_bots.active().count()
        context["total_invested"] = all_bots.active().total_invested()
        context["total_pnl"] = all_bots.active().total_pnl()

        return context


class BotDetailView(DetailView):
    """Detail view for a single bot with events history."""

    model = Bot
    template_name = "bots/bot_detail.html"
    context_object_name = "bot"

    def get_queryset(self):
        """Include related trading pair."""
        return Bot.objects.select_related("trading_pair")

    def get_context_data(self, **kwargs):
        """Add bot events to context."""
        context = super().get_context_data(**kwargs)
        context["events"] = self.object.events.all()[:20]
        return context


class BotCreateView(CreateView):
    """View for creating a new bot."""

    model = Bot
    template_name = "bots/bot_create.html"
    fields = ["bot_type", "trading_pair", "invested_amount", "params", "is_simulated"]
    success_url = reverse_lazy("bots:bot_list")

    def get_context_data(self, **kwargs):
        """Add bot types and trading pairs to context."""
        context = super().get_context_data(**kwargs)
        context["bot_types"] = BotType.choices
        context["trading_pairs"] = TradingPair.objects.active()
        return context

    def form_valid(self, form):
        """Set initial status and create bot event."""
        form.instance.status = BotStatus.PENDING
        # Generate a placeholder bot ID (in real usage, this comes from Pionex API)
        import uuid

        form.instance.pionex_bot_id = f"sim_{uuid.uuid4().hex[:12]}"

        response = super().form_valid(form)

        # Create bot creation event
        BotEvent.objects.create(
            bot=self.object,
            event_type=BotEvent.EventType.CREATED,
            details={"params": form.instance.params},
            reasoning="Bot created via dashboard",
        )

        messages.success(self.request, f"Bot {self.object.pionex_bot_id} created successfully.")
        return response


class BotStopView(View):
    """View for stopping a bot."""

    def post(self, request, pk):
        """Stop the bot and create event."""
        from django.utils import timezone

        try:
            bot = Bot.objects.get(pk=pk)

            if bot.status != BotStatus.ACTIVE:
                messages.warning(request, f"Bot {bot.pionex_bot_id} is not active.")
                return redirect("bots:bot_detail", pk=pk)

            # Get stop reason from form
            reason = request.POST.get("reason", "Stopped via dashboard")

            # Update bot status
            bot.status = BotStatus.STOPPED
            bot.stopped_at = timezone.now()
            bot.stop_reason = reason
            bot.save()

            # Create stop event
            BotEvent.objects.create(
                bot=bot,
                event_type=BotEvent.EventType.STOPPED,
                details={"previous_status": BotStatus.ACTIVE},
                reasoning=reason,
            )

            messages.success(request, f"Bot {bot.pionex_bot_id} stopped successfully.")

        except Bot.DoesNotExist:
            messages.error(request, "Bot not found.")

        return redirect("bots:bot_list")
