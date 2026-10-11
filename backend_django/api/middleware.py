from django.http import JsonResponse
from django.contrib.auth import logout

class BannedUserMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            if hasattr(request.user, 'profile') and request.user.profile.banned:
                logout(request)
                if request.path.startswith('/api/'):
                    return JsonResponse({'error': '你已被封禁，详情咨询管理员', 'banned': True}, status=403)
        return self.get_response(request)
