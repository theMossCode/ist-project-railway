from django import forms

from .models import Topic, DataObject


class NewProjectForm(forms.Form):
    name = forms.CharField(label="name", max_length=32)
    desc = forms.CharField(label="desc", max_length=256, required=False)
    mqtt_host = forms.CharField(label="mqtt_host", max_length=32)
    mqtt_port = forms.IntegerField(label="mqtt_port")
    mqtt_username = forms.CharField(label="username", max_length=32, required=False)
    mqtt_password = forms.CharField(label="password", max_length=32, required=False)


class NewTopicForm(forms.Form):
    name = forms.CharField(label="name", max_length=32)
    desc = forms.CharField(label="desc", max_length=256, required=False)
    path = forms.CharField(label="path", max_length=64)
    sub = forms.CharField(max_length=5, label="sub")
    qos = forms.ChoiceField(choices=Topic.QOS_CHOICES, label="qos")


class NewDataObjectForm(forms.Form):
    name = forms.CharField(label="name", max_length=32)
    desc = forms.CharField(label="desc", max_length=256, required=False)
    data_type = forms.ChoiceField(label="data_type", choices=DataObject.DATA_TYPE_CHOICES)
    path = forms.CharField(label="path", max_length=64, required=False)
    format = forms.ChoiceField(label="format", choices=DataObject.FORMAT_CHOICES)
    key = forms.CharField(label="key", max_length=32, required=False)
    widget_type = forms.ChoiceField(label="widget_type", choices=DataObject.WIDGET_TYPE_CHOICES)

