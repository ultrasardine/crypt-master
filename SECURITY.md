# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |

## Reporting a Vulnerability

If you discover a security vulnerability, please report it by creating a private security advisory on GitHub or by opening an issue.

Please include:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

We will respond as quickly as possible and work with you to address the issue.

## Security Considerations

Crypt Master handles sensitive financial data and API credentials. Please be aware:

### API Credentials
- Never commit API keys or secrets to version control
- Use environment variables for all sensitive configuration
- The `.env` file is gitignored by default

### Trading Operations
- Always start with `DRY_RUN=True` to test strategies
- Review risk management settings before live trading
- Monitor bot activity and set appropriate loss thresholds

### Network Security
- Use HTTPS in production
- Configure `ALLOWED_HOSTS` properly
- Keep dependencies updated

### Database Security
- Use strong passwords for PostgreSQL
- Restrict database access to necessary services
- Regular backups are recommended

## Best Practices

1. Keep all dependencies updated
2. Review logs regularly for suspicious activity
3. Use the principle of least privilege for API keys
4. Test thoroughly in dry-run mode before live trading
