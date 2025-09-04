from django.urls import path
from . import views

app_name = 'api'

urlpatterns = [
    path('status/', views.api_status, name='status'),
]