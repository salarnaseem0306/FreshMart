from rest_framework import serializers


class MeResponseSerializer(serializers.Serializer):
    username = serializers.CharField()
    role = serializers.CharField()