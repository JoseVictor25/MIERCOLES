from django.urls import path
from .views import project_chat, project_ai_settings

urlpatterns = [
    path("projects/<int:pk>/chat/", project_chat, name="project-chat"),
    path("projects/<int:pk>/ai-settings/", project_ai_settings, name="project-ai-settings"),
]
