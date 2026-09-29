from django.contrib import admin
from django.urls import path

from surveryBackend import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/csrf/', views.request_csrf_token),
    path('api/responses/', views.submit_response),
    path('api/problem-logs/', views.submit_supporter_problem),
    path('api/links/', views.issue_link),
    path('api/qr-codes/', views.issue_qr_code),
]
