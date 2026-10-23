from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        MANAGER = "manager", "Manager"
        CASHIER = "cashier", "Cashier"

    role = models.CharField(
        max_length=10, choices=Role.choices, default=Role.CASHIER
    )

    def __str__(self):
        return f"{self.username} ({self.role})"