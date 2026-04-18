from django.urls import path
from . import views

urlpatterns = [
    path('', views.control_panel, name='door_control_panel'),
    path('action/', views.control_action, name='door_control_action'),
    path('camera/stream/', views.camera_stream, name='door_control_camera_stream'),
]
