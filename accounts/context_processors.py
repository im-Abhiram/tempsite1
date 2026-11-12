"""
Thamarayyath Employee Portal — Template Context Processor.
Injects globally needed values into every template context.
"""

from .models import CompanySettings


def portal_context(request):
    """
    Makes company name, currency, and the current user's role
    available in all templates without manual context passing.
    """
    ctx = {
        "PORTAL_NAME": "Thamarayyath Employee Portal",
        "COMPANY_NAME": "Thamarayyath",
        "CURRENCY_SYMBOL": "₹",
    }

    if request.user.is_authenticated:
        try:
            settings = CompanySettings.get()
            ctx["COMPANY_NAME"] = settings.company_name
            ctx["CURRENCY_SYMBOL"] = settings.currency_symbol
            ctx["company_settings"] = settings
        except Exception:
            pass

        ctx["current_user_role"] = request.user.role
        ctx["is_superadmin"] = request.user.is_superadmin
        ctx["is_office_admin"] = request.user.is_office_admin
        ctx["is_accountant"] = request.user.is_accountant
        ctx["is_owner"] = request.user.is_owner

    return ctx
