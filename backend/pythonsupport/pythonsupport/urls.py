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
    # On the server, nginx (managed by DTU) forwards every request here, so Django serves the
    # admin's CSS/JS and the frontend itself. In development, runserver serves /static/ first.
    # ponytail: django's serve() is slow; add WhiteNoise if traffic grows.
    re_path(r'^static/(?P<path>.*)$', serve, {'document_root': settings.STATIC_ROOT}),
    # Frontend last, so the API and admin routes win.
    path('', serve, {'document_root': FRONTEND_DIR, 'path': 'index.html'}),
    re_path(r'^(?P<path>.*)$', serve, {'document_root': FRONTEND_DIR}),
]
