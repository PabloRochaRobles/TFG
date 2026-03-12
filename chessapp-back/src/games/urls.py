from django.urls import path
from .views import (
    VideoUploadView, delete_video_and_frames, AnalyzeVideoView, VideoStreamView,
    VideoListView, AnalysisChainView, FensView,
    VideoFirstFrameView, CalibrateCornersView, AnalysisProgressView,
)

urlpatterns = [
    path('upload/', VideoUploadView.as_view(), name='video_upload'),
    path('delete/<str:file_name>/', delete_video_and_frames, name='video_delete'),
    path('analyze/', AnalyzeVideoView.as_view(), name='video_analyze'),
    path('progress/<str:file_name>/', AnalysisProgressView.as_view(), name='analysis_progress'),
    path('stream/<str:file_name>/', VideoStreamView.as_view(), name='video_stream'),
    path('list/', VideoListView.as_view(), name='video_list'),
    path('analysis-chain/', AnalysisChainView.as_view(), name='analysis_chain'),
    path('fens/<str:analysis_id>/', FensView.as_view(), name='fens_get'),
    path('first-frame/<str:file_name>/', VideoFirstFrameView.as_view(), name='first_frame'),
    path('calibrate/', CalibrateCornersView.as_view(), name='calibrate_corners'),
]