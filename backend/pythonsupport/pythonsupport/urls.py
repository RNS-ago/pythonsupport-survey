from django.conf import settings
from django.contrib import admin
from django.urls import path, re_path
from django.views.static import serve

from surveryBackend import views

# repo/frontend, next to repo/backend
FRONTEND_DIR = settings.BASE_DIR.parent.parent / 'frontend'

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/csrf/', views.request_csrf_token),
    path('api/responses/', views.submit_response),
    path('api/problem-logs/', views.submit_supporter_problem),
    path('api/links/', views.issue_link),
    path('api/qr-codes/', views.issue_qr_code),
    # Frontend last, so the API and admin routes win.
    # ponytail: django's serve() is slow; put Caddy/WhiteNoise in front if traffic grows.
    path('', serve, {'document_root': FRONTEND_DIR, 'path': 'index.html'}),
    re_path(r'^(?P<path>.*)$', serve, {'document_root': FRONTEND_DIR}),
]
