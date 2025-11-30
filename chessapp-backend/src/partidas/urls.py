from djanjo.urls import path
from views import VideoUploadView

urlpatterns = [
    path("upload", VideoUploadView.as_view(), name="video_upload"),
]