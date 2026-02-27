from django.urls import path
from .views import VideoUploadView, delete_video_and_frames, AnalyzeVideoView, VideoStreamView, VideoListView, AnalysisChainView

urlpatterns = [
    path('upload/', VideoUploadView.as_view(), name='video_upload'),
    path('delete/<str:file_name>/', delete_video_and_frames, name='video_delete'),
    path('analyze/', AnalyzeVideoView.as_view(), name='video_analyze'),
    path('stream/<str:file_name>/', VideoStreamView.as_view(), name='video_stream'),
    path('list/', VideoListView.as_view(), name='video_list'),
    path('analysis-chain/', AnalysisChainView.as_view(), name='analysis_chain'),
]