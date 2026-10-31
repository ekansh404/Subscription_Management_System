from django.shortcuts import redirect
from django.utils.http import url_has_allowed_host_and_scheme


def redirect_next(request, fallback):
    """
    Redirect to the ``next`` value posted by a form when it points to this
    site, otherwise to ``fallback``. Prevents open redirects to other domains.
    """
    target = request.POST.get("next") or request.GET.get("next")
    if target and url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return redirect(target)
    return redirect(fallback)
