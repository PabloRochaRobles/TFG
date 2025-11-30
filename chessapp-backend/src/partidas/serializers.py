from rest_framework import serializers

class VideoUploadSerializer(serializers.Serializer):
    video = serializers.FileField(required=True)


