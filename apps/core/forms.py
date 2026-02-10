"""
Core app forms for user registration and profile management.

Requirements:
- 1.1: Create UserProfile with default settings on user registration
- 1.2: Persist user preference changes
- 1.3: Store user preferences (trading mode, notifications, risk tolerance)
- 2.5: Securely overwrite previous encrypted values on update
- 2.6: Securely remove encrypted data on deletion
"""

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from .models import UserProfile


class UserRegistrationForm(UserCreationForm):
    """
    Form for user registration.

    Extends Django's UserCreationForm to include email field.
    UserProfile is auto-created via signal when User is saved.

    Requirements:
    - 1.1: Create UserProfile with default settings on user registration
    """

    email = forms.EmailField(
        required=True,
        help_text="Required. Enter a valid email address.",
        widget=forms.EmailInput(
            attrs={
                "placeholder": "Enter your email",
                "autocomplete": "email",
            }
        ),
    )

    class Meta:
        model = User
        fields = ["username", "email", "password1", "password2"]
        widgets = {
            "username": forms.TextInput(
                attrs={
                    "placeholder": "Choose a username",
                    "autocomplete": "username",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Add placeholders to password fields
        self.fields["password1"].widget.attrs.update(
            {
                "placeholder": "Enter password",
                "autocomplete": "new-password",
            }
        )
        self.fields["password2"].widget.attrs.update(
            {
                "placeholder": "Confirm password",
                "autocomplete": "new-password",
            }
        )

    def save(self, commit=True):
        """
        Save the user and ensure email is set.

        The UserProfile is automatically created via the post_save signal
        on the User model.
        """
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        if commit:
            user.save()
        return user


class UserProfileForm(forms.ModelForm):
    """
    Form for editing user profile settings.

    Excludes encrypted API key fields - those are handled separately.

    Requirements:
    - 1.2: Persist user preference changes
    - 1.3: Store user preferences (trading mode, notifications, risk tolerance)
    """

    # Override JSONField with CharField to accept comma-separated input
    active_trading_pairs = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "placeholder": "Enter trading pairs (e.g., BTC_USDT, ETH_USDT)",
                "class": "config-input",
            }
        ),
        help_text="Comma-separated list of trading pairs you want to monitor.",
    )

    class Meta:
        model = UserProfile
        fields = [
            "default_trading_mode",
            "risk_tolerance",
            "notification_email_enabled",
            "active_trading_pairs",
        ]
        widgets = {
            "default_trading_mode": forms.Select(
                attrs={"class": "config-input"},
            ),
            "risk_tolerance": forms.Select(
                attrs={"class": "config-input"},
            ),
            "notification_email_enabled": forms.CheckboxInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Convert active_trading_pairs list to comma-separated string for display
        if self.instance and self.instance.active_trading_pairs:
            self.initial["active_trading_pairs"] = ", ".join(
                self.instance.active_trading_pairs
            )

    def clean_active_trading_pairs(self):
        """
        Convert comma-separated string to list of trading pairs.
        """
        value = self.cleaned_data.get("active_trading_pairs", "")
        if isinstance(value, str):
            # Split by comma and clean up whitespace
            pairs = [p.strip().upper() for p in value.split(",") if p.strip()]
            return pairs
        return value if value else []

    def save(self, commit=True):
        """
        Save the profile and ensure trading pairs exist in the database.

        This auto-creates TradingPair records for any symbols the user adds
        to their active_trading_pairs list.
        """
        instance = super().save(commit=False)

        # Auto-create TradingPair records for user's active pairs
        if instance.active_trading_pairs:
            from .models import TradingPair

            TradingPair.objects.ensure_pairs_exist(instance.active_trading_pairs)

        if commit:
            instance.save()
        return instance


class APIKeyForm(forms.Form):
    """
    Form for setting Pionex API credentials.

    Requirements:
    - 2.5: Securely overwrite previous encrypted values on update
    - 2.7: Validate API key format before encryption
    """

    api_key = forms.CharField(
        min_length=16,
        max_length=128,
        widget=forms.TextInput(
            attrs={
                "placeholder": "Enter your Pionex API key",
                "autocomplete": "off",
                "class": "config-input",
            }
        ),
        help_text="Your Pionex API key (16-128 alphanumeric characters)",
    )
    api_secret = forms.CharField(
        min_length=16,
        max_length=128,
        widget=forms.PasswordInput(
            attrs={
                "placeholder": "Enter your Pionex API secret",
                "autocomplete": "off",
                "class": "config-input",
            }
        ),
        help_text="Your Pionex API secret (16-128 alphanumeric characters)",
    )

    def clean_api_key(self):
        """Validate API key format."""
        from lib.crypto.api_key_manager import APIKeyManager

        api_key = self.cleaned_data.get("api_key", "")
        manager = APIKeyManager(master_key="validation-only")

        if not manager.validate_api_key_format(api_key):
            raise forms.ValidationError(
                "Invalid API key format. Must be 16-128 alphanumeric characters."
            )
        return api_key

    def clean_api_secret(self):
        """Validate API secret format."""
        from lib.crypto.api_key_manager import APIKeyManager

        api_secret = self.cleaned_data.get("api_secret", "")
        manager = APIKeyManager(master_key="validation-only")

        if not manager.validate_api_key_format(api_secret):
            raise forms.ValidationError(
                "Invalid API secret format. Must be 16-128 alphanumeric characters."
            )
        return api_secret

    def save(self, profile: UserProfile) -> None:
        """
        Save API credentials to the user profile.

        Args:
            profile: The UserProfile instance to update.

        Raises:
            APIKeyValidationError: If the API key format is invalid.
        """
        api_key = self.cleaned_data["api_key"]
        api_secret = self.cleaned_data["api_secret"]
        profile.set_api_credentials(api_key, api_secret)


class ExternalAPIKeyForm(forms.Form):
    """
    Form for setting external data source API credentials.

    Supports on-chain (Glassnode/IntoTheBlock) and social sentiment
    (LunarCrush/Santiment) API keys.
    """

    onchain_api_key = forms.CharField(
        required=False,
        min_length=8,
        max_length=256,
        widget=forms.PasswordInput(
            attrs={
                "placeholder": "Enter your Glassnode or IntoTheBlock API key",
                "autocomplete": "off",
                "class": "config-input",
            }
        ),
        help_text="API key for on-chain metrics (Glassnode or IntoTheBlock)",
    )
    social_api_key = forms.CharField(
        required=False,
        min_length=8,
        max_length=256,
        widget=forms.PasswordInput(
            attrs={
                "placeholder": "Enter your LunarCrush or Santiment API key",
                "autocomplete": "off",
                "class": "config-input",
            }
        ),
        help_text="API key for social sentiment (LunarCrush or Santiment)",
    )

    def clean(self):
        """Ensure at least one API key is provided."""
        cleaned_data = super().clean()
        onchain_key = cleaned_data.get("onchain_api_key", "").strip()
        social_key = cleaned_data.get("social_api_key", "").strip()

        if not onchain_key and not social_key:
            raise forms.ValidationError(
                "Please provide at least one API key to save."
            )

        return cleaned_data

    def save(self, profile: UserProfile) -> dict[str, bool]:
        """
        Save external API keys to the user profile.

        Args:
            profile: The UserProfile instance to update.

        Returns:
            Dict indicating which keys were saved.
        """
        saved = {"onchain": False, "social": False}

        onchain_key = self.cleaned_data.get("onchain_api_key", "").strip()
        social_key = self.cleaned_data.get("social_api_key", "").strip()

        if onchain_key:
            profile.set_onchain_api_key(onchain_key)
            saved["onchain"] = True

        if social_key:
            profile.set_social_api_key(social_key)
            saved["social"] = True

        return saved
