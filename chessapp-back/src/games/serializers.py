from rest_framework import serializers

class VideoUploadSerializer(serializers.Serializer):
    video_file = serializers.FileField(required=True)