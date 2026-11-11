from django.urls import path
from .views import project_chat, project_ai_settings, upload_chat_image, chat_image_file, analyze_chat_image

urlpatterns = [
    path("projects/<int:pk>/chat/", project_chat, name="project-chat"),
    path("projects/<int:pk>/ai-settings/", project_ai_settings, name="project-ai-settings"),
    path("projects/<int:pk>/chat/images/", upload_chat_image, name="project-chat-image-upload"),
    path("projects/<int:pk>/chat/<int:message_id>/image/", chat_image_file, name="project-chat-image-file"),
    path("projects/<int:pk>/chat/<int:message_id>/analyze/", analyze_chat_image, name="project-chat-image-analyze"),
]
