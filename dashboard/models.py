from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone
from django.urls import reverse


class BaseModel(models.Model):
    name = models.CharField(max_length=32)
    description = models.TextField(max_length=256)

    def __str__(self):
        return self.name

    class Meta:
        abstract = True


class Project(BaseModel):
    host = models.CharField(max_length=64)
    port = models.IntegerField()
    username = models.CharField(max_length=32, null=True, blank=True)
    password = models.CharField(max_length=32, null=True, blank=True)
    connected = models.BooleanField(default=False)
    created_date = models.DateTimeField(default=timezone.datetime.now())
    db_name = models.CharField(max_length=64)

    class Meta:
        permissions = (
            ("is_owner", "Has all permissions"),
            ("can_add", "Can create new project"),
            ("can_delete", "Can delete project"),
            ("can_view", "View only permission"),
        )


class Topic(BaseModel):
    QOS_CHOICES = [
        (0, "0 (At Most Once)"),
        (1, "1 (At Least Once)"),
        (2, "2 (Exactly Once)")
    ]

    path = models.CharField(max_length=64, default="/")
    sub = models.BooleanField(default=True)
    pub = models.BooleanField(default=False)
    qos = models.IntegerField(default=0, choices=QOS_CHOICES)
    project = models.ForeignKey(Project, on_delete=models.CASCADE)


class DataObject(BaseModel):
    FORMAT_CHOICE_JSON = "JSON"
    FORMAT_CHOICE_SINGLE_VARIABLE = "SINGL"
    FORMAT_CHOICES = [
        (FORMAT_CHOICE_JSON, "JSON"),
        (FORMAT_CHOICE_SINGLE_VARIABLE, "Single Variable"),
    ]

    DATA_TYPE_NUMBER = "NUM"
    DATA_TYPE_STRING = "STR"
    DATA_TYPE_LOCATION = "LOC"
    DATA_TYPE_BOOLEAN = "BOOL"
    DATA_TYPE_CHOICES = [
        (DATA_TYPE_NUMBER, "Number"),
        (DATA_TYPE_STRING, "String"),
        (DATA_TYPE_LOCATION, "Location"),
        (DATA_TYPE_BOOLEAN, "Boolean"),
    ]

    WIDGET_TYPE_SCATTER = "SCATTER"
    WIDGET_TYPE_LINE = "LINE"
    WIDGET_TYPE_STATUS = "STATUS"
    WIDGET_TYPE_MAP = "MAP"
    WIDGET_TYPE_CHOICES = [
        (WIDGET_TYPE_SCATTER, "Scatter Plot"),
        (WIDGET_TYPE_LINE, "Line plot"),
        (WIDGET_TYPE_STATUS, "Status Indicator"),
        (WIDGET_TYPE_MAP, "Map")
    ]

    format = models.CharField(max_length=5, choices=FORMAT_CHOICES)
    data_type = models.CharField(max_length=5, choices=DATA_TYPE_CHOICES)
    widget_type = models.CharField(max_length=10, choices=WIDGET_TYPE_CHOICES, default=WIDGET_TYPE_LINE)
    path = models.CharField(max_length=64, null=True, blank=True)
    key = models.CharField(max_length=32, null=True, blank=True)
    topic = models.ForeignKey(Topic, on_delete=models.CASCADE)
