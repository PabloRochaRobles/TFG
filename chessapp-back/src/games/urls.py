from django.urls import path
from .views import VideoUploadView, delete_video_and_frames, AnalyzeVideoView, VideoStreamView, VideoListView

urlpatterns = [
    path('upload/', VideoUploadView.as_view(), name='video_upload'),
    path('delete/', delete_video_and_frames, name='video_delete'),
    path('analyze/', AnalyzeVideoView.as_view(), name='video_analyze'),
    path('stream/<str:file_name>/', VideoStreamView.as_view(), name='video_stream'),
    path('list/', VideoListView.as_view(), name='video_list'),
]