from rest_framework import serializers


class DailyQuerySerializer(serializers.Serializer):
    date = serializers.DateField(required=False)


class TopProductsQuerySerializer(serializers.Serializer):
    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)
    limit = serializers.IntegerField(required=False, min_value=1, max_value=100, default=10)