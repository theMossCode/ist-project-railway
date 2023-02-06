import asyncio
import concurrent.futures
import csv
import logging
import datetime
import time

import django.db.models
import pymongo
from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse, StreamingHttpResponse
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user
from django.utils.decorators import method_decorator

from guardian.shortcuts import assign_perm, get_perms, get_objects_for_user

from asgiref.sync import async_to_sync, sync_to_async
# from channels.layers import get_channel_layer

from .forms import NewProjectForm, NewTopicForm, NewDataObjectForm
from .models import Project, Topic, DataObject
from .mongodb import get_db_name, db_utils
from .bokeh_utils import BokehPlot
from .mqtt import mqtt_client_manager
from . import utils

from django.views.generic import TemplateView
from django.views import View


# channel_layer = get_channel_layer()
detail_decorators = [login_required(login_url="authentication:login")]


class ViewsMixin:
    required_permissions = None
    user = None
    context = dict()
    template_name = None
    form_class = None

    def set_template_name(self, t_name):
        self.template_name = t_name

    def set_required_permissions(self, permissions_list):
        self.required_permissions = permissions_list

    def set_form_class(self, f_class):
        self.form_class = f_class

    def clear_context(self):
        self.context.clear()

    def add_context_data(self, key, value):
        self.context[str(key)] = value

    def get_topics_for_project(self, project):
        topics = Topic.objects.filter(project=project)
        return topics

    def get_dataobjects_for_topic(self, topic):
        data_objects = DataObject.objects.filter(topic=topic)
        return data_objects

    def get_project(self, project_id):
        try:
            project = Project.objects.get(pk=project_id)
            return project
        except django.db.models.ObjectDoesNotExist:
            return None

    def get_topic(self, topic_id):
        try:
            topic = Topic.objects.get(pk=topic_id)
            return topic
        except django.db.models.ObjectDoesNotExist:
            return None

    def get_data_object(self, dataobject_id):
        try:
            data_object = DataObject.objects.get(pk=dataobject_id)
            return data_object
        except django.db.models.ObjectDoesNotExist:
            return None

    def get_projects(self):
        if not self.user:
            return None
        try:
            projects = get_objects_for_user(self.user, self.required_permissions, any_perm=True)
            return projects
        except django.db.models.ObjectDoesNotExist:
            return None

    def get_projects_param_list(self):
        projects = self.get_projects()
        projects_param_list = list()
        for project in projects:
            topics = self.get_topics_for_project(project)
            mqtt_client = mqtt_client_manager.get_client(project.pk)
            if mqtt_client:
                connected = mqtt_client.connected
            else:
                connected = False

            project_params = {
                "project": project,
                "connected": connected
            }
            projects_entry = {
                "project_params": project_params,
                "topics": topics
            }

            projects_param_list.append(projects_entry)

        return projects_param_list

    def render_template(self, request):
        return render(request, self.template_name, self.context)


@method_decorator(detail_decorators, name="dispatch")
class IndexView(ViewsMixin, TemplateView):
    def __init__(self):
        # super().__init__()
        self.set_template_name("dashboard/index/index.html")
        self.set_required_permissions([
            "dashboard.is_owner",
            "dashboard.can_view",
            "dashboard.can_delete",
        ])

    def get_context_data(self, **kwargs):
        self.clear_context()
        self.context = super().get_context_data(**kwargs)
        self.user = get_user(self.request)
        self.add_context_data("user", self.user)
        self.add_context_data("project_list", self.get_projects_param_list())
        return self.context


@method_decorator(detail_decorators, name="dispatch")
class DetailProjectView(ViewsMixin, TemplateView):
    def __init__(self):
        super().__init__()
        self.set_template_name("dashboard/detail/project.html")

    def get_context_data(self, **kwargs):
        self.clear_context()
        self.context = super().get_context_data()
        project = self.get_project(kwargs["project_id"])
        topics = self.get_topics_for_project(project)
        self.add_context_data("project", project)
        self.add_context_data("topics", topics)
        return self.context


@method_decorator(detail_decorators, name="dispatch")
class DetailTopicView(ViewsMixin, TemplateView):
    def __init__(self):
        super().__init__()
        self.set_template_name("dashboard/detail/topic.html")

    def get_context_data(self, **kwargs):
        self.clear_context()
        self.context = super().get_context_data(**kwargs)
        topic = self.get_topic(kwargs["topic_id"])
        data_objects = self.get_dataobjects_for_topic(topic)
        self.add_context_data("topic", topic)
        self.add_context_data("data_objects", data_objects)
        return self.context


@method_decorator(detail_decorators, name="dispatch")
class DetailDataObjectView(ViewsMixin, TemplateView):
    def __init__(self):
        super().__init__()
        self.set_template_name("dashboard/detail/dataobject.html")

    def get_context_data(self, **kwargs):
        self.clear_context()
        self.context = super().get_context_data(**kwargs)
        data_object = self.get_data_object(kwargs["dataobject_id"])
        topic = self.get_topic(data_object.topic.pk)
        project = self.get_project(topic.project.pk)
        self.add_context_data("dataobject", data_object)
        self.add_context_data("topic", topic)
        self.add_context_data("project", project)
        return self.context


"""
New Views
"""


class NewProjectView(ViewsMixin, View):
    def __init__(self):
        super().__init__()
        self.set_template_name("dashboard/modals/new_project.html")
        self.set_form_class(NewProjectForm)

    def get(self, request, *args, **kwargs):
        initial = {"mqtt_port": 1883}
        self.user = get_user(request)
        if not self.user.is_authenticated:
            return HttpResponse(status=403)

        form = self.form_class(initial=initial)
        self.clear_context()
        self.add_context_data("form", form)
        return self.render_template(request)

    def post(self, request, *args, **kwargs):
        self.user = get_user(request)
        if not self.user.is_authenticated:
            return HttpResponse(status=403)

        self.clear_context()
        form = self.form_class(request.POST)
        if form.is_valid():
            project = Project(
                name=form.cleaned_data["name"],
                description=form.cleaned_data["desc"],
                host=form.cleaned_data["mqtt_host"],
                port=form.cleaned_data["mqtt_port"],
                username=form.cleaned_data["mqtt_username"],
                password=form.cleaned_data["mqtt_password"],
                db_name=get_db_name(self.user),
            )

            try:
                project.save()
            except:
                form.add_error(None, "Unknown error!!")
                self.add_context_data("form", form)
                return self.render_template(request)

            assign_perm("is_owner", self.user, project)
            mqtt_client_manager.add_client(
                client_id=project.pk,
                host=project.host,
                port=project.port,
                userdata=None
            )
            mqtt_client_manager.connect_client(project.pk)
            mqtt_client_manager.start_client(project.pk)
            return HttpResponse(status=201)
        else:
            form.add_error(None, "Form not valid. Please review form and update.")
            self.add_context_data("form", form)
            return self.render_template(request)


class NewTopicView(ViewsMixin, View):
    qos_choices = Topic.QOS_CHOICES

    def __init__(self):
        super().__init__()
        self.set_template_name("dashboard/modals/new_topic.html")
        self.set_form_class(NewTopicForm)

    def subscribe_mqtt_topic(self, project, topic):
        _client = mqtt_client_manager.get_client(project.pk)
        if not _client:
            logging.debug("Not valid client")
            return False

        return async_to_sync(_client.subscribe_topic)(
            topic=topic.path,
            qos=topic.qos
        )

    def get(self, request, *args, **kwargs):
        self.user = get_user(request)
        if not self.user.is_authenticated:
            return HttpResponse(status=403)

        self.clear_context()
        project = self.get_project(kwargs["project_id"])
        initial = {
            "project_id": project.pk,
        }
        form = self.form_class(initial=initial)
        self.add_context_data("form", form)
        self.add_context_data("project", project)
        self.add_context_data("qos_choices", self.qos_choices)
        return self.render_template(request)

    def post(self, request, *args, **kwargs):
        self.user = get_user(request)
        if not self.user.is_authenticated:
            return HttpResponse(status=403)

        self.clear_context()
        project = self.get_project(kwargs["project_id"])
        form = self.form_class(request.POST)
        if form.is_valid():
            topic = Topic(
                name=form.cleaned_data["name"],
                description=form.cleaned_data["desc"],
                path=form.cleaned_data["path"],
                sub=form.cleaned_data["sub"] == "sub",
                pub=form.cleaned_data["sub"] == "pub",
                qos=form.cleaned_data["qos"],
                project=project,
            )

            saved_topics = self.get_topics_for_project(project)
            for s_topic in saved_topics:
                if topic.name == s_topic.name:
                    form.add_error(None, "Name already exists")
                    return self.render_template(request)

            try:
                topic.save()
            except:
                form.add_error(None, "Unknown Error!!")
                return self.render_template(request)

            self.subscribe_mqtt_topic(project, topic)
            return HttpResponse(status=201)
        else:
            form.add_error(None, "Invalid form!")
            return self.render_template(request)


class NewDataObject(ViewsMixin, View):
    def __init__(self):
        super().__init__()
        self.set_template_name("dashboard/modals/new_dataobject.html")
        self.set_form_class(NewDataObjectForm)

    def get(self, request, *args, **kwargs):
        self.clear_context()
        topic = self.get_topic(kwargs["topic_id"])
        form = self.form_class()
        self.add_context_data("topic", topic)
        self.add_context_data("form", form)
        self.add_context_data("format_choices", DataObject.FORMAT_CHOICES)
        self.add_context_data("data_types", DataObject.DATA_TYPE_CHOICES)
        self.add_context_data("widget_types", DataObject.WIDGET_TYPE_CHOICES)
        return self.render_template(request)

    def post(self, request, *args, **kwargs):
        self.clear_context()
        topic = self.get_topic(kwargs["topic_id"])
        form = self.form_class(request.POST)
        self.add_context_data("topic", topic)
        self.add_context_data("form", form)
        self.add_context_data("format_choices", DataObject.FORMAT_CHOICES)
        self.add_context_data("data_types", DataObject.DATA_TYPE_CHOICES)
        self.add_context_data("widget_types", DataObject.WIDGET_TYPE_CHOICES)

        if form.is_valid():
            if (not form.cleaned_data["key"]) and (form.cleaned_data["format"] == DataObject.FORMAT_CHOICE_JSON):
                form.add_error(None, "Key required for JSON types")
                return self.render_template(request)

            data_object = DataObject(
                name=form.cleaned_data["name"],
                description=form.cleaned_data["desc"],
                format=form.cleaned_data["format"],
                data_type=form.cleaned_data["data_type"],
                path=form.cleaned_data["path"],
                key=form.cleaned_data["key"],
                topic=topic,
                widget_type=form.cleaned_data["widget_type"]
            )
            try:
                data_object.save()
                return HttpResponse(status=201)
            except:
                form.add_error(None, "Unknown error occurred!")
                return self.render_template(request)
        else:
            form.add_error(None, "Form invalid!")
            return self.render_template(request)


"""
Delete
"""
class DeleteProjectView(ViewsMixin, View):
    def __init__(self):
        super().__init__()
        self.set_template_name("dashboard/index/include/index_content.html")
        self.set_required_permissions([
            "dashboard.is_owner",
            "dashboard.can_delete",
        ])

    def get(self, request, *args, **kwargs):
        self.user = get_user(request)
        project = self.get_project(kwargs["project_id"])
        user_permissions = get_perms(self.user, project)
        logging.debug(f"User perms: {user_permissions}, required: {self.required_permissions}")

        if ("is_owner" not in user_permissions) and ("can_delete" not in user_permissions):
            return HttpResponse(status=500)

        with concurrent.futures.ThreadPoolExecutor() as pool:
            fut = pool.submit(
                db_utils.delete_project_collection, project
            )

            if not fut.result():
                return HttpResponse(status=500)

        mqtt_client_manager.delete_client(project.pk)
        project.delete()
        self.clear_context()
        self.add_context_data("project_list", self.get_projects_param_list())
        return self.render_template(request)


class DeleteTopicView(ViewsMixin, View):
    def __init__(self):
        super().__init__()
        self.set_template_name("dashboard/detail/include/project_content.html")
        self.set_required_permissions([
            "dashboard.is_owner",
            "dashboard.can_delete",
        ])

    def get(self, request, *args, **kwargs):
        topic = self.get_topic(kwargs["topic_id"])
        project = self.get_project(topic.project.pk)
        with concurrent.futures.ThreadPoolExecutor() as pool:
            fut = pool.submit(
                db_utils.delete_topic_documents, project, topic
            )

            if not fut.result():
                return HttpResponse(status=500)

        self.unsubscribe_mqtt_topic(project, topic)
        topic.delete()
        self.clear_context()
        self.add_context_data("project", project)
        self.add_context_data("topics", self.get_topics_for_project(project))
        return self.render_template(request)

    def unsubscribe_mqtt_topic(self, project, topic):
        _client = mqtt_client_manager.get_client(project.pk)
        if not _client:
            logging.error("No valid client")
            return

        async_to_sync(_client.unsubscribe_topic)(topic.path)


class DeleteDataObject(ViewsMixin, View):
    def __init__(self):
        super().__init__()
        self.set_template_name("dashboard/detail/include/topic_content.html")
        self.set_required_permissions([
            "dashboard.is_owner",
            "dashboard.can_delete",
        ])

    def get(self, request, *args, **kwargs):
        data_object = self.get_data_object(kwargs["dataobject_id"])
        topic = self.get_topic(data_object.topic.pk)
        project = self.get_project(topic.project.pk)
        with concurrent.futures.ThreadPoolExecutor() as pool:
            fut = pool.submit(
                db_utils.delete_dataobject, project, topic, data_object
            )

            res = fut.result()
            if not res:
                return HttpResponse(status=500)

        data_object.delete()
        self.clear_context()
        self.add_context_data("topic", topic)
        self.add_context_data("data_objects", self.get_dataobjects_for_topic(topic))
        return self.render_template(request)


class EditDataObjectView(ViewsMixin, View):
    context = {
        "format_choices": DataObject.FORMAT_CHOICES,
        "data_types": DataObject.DATA_TYPE_CHOICES,
        "widget_types": DataObject.WIDGET_TYPE_CHOICES,
    }

    def __init__(self):
        super().__init__()
        self.set_template_name("dashboard/modals/edit_dataobject.html")
        self.set_form_class(NewDataObjectForm)

    def get(self, request, *args, **kwargs):
        data_object = self.get_data_object(kwargs["dataobject_id"])
        topic = self.get_topic(data_object.topic.pk)
        initial = {
            "name": data_object.name,
            "desc": data_object.description,
            "data_type": data_object.data_type,
            "path": data_object.path,
            "format": data_object.format,
            "key": data_object.key,
        }

        form = self.form_class(initial)
        self.add_context_data("form", form)
        self.add_context_data("dataobject", data_object)
        return self.render_template(request)

    def post(self, request, *args, **kwargs):
        data_object = self.get_data_object(kwargs["dataobject_id"])
        form = self.form_class(request.POST)
        self.add_context_data("form", form)
        self.add_context_data("dataobject", data_object)
        if not form.has_changed():
            return HttpResponse(status=201)
        elif form.is_valid():
            data_object.name = form.cleaned_data.get("name", data_object.name)
            data_object.description = form.cleaned_data.get("desc", data_object.description)
            data_object.path = form.cleaned_data.get("path", data_object.path)
            data_object.key = form.cleaned_data.get("key", data_object.key)
            data_object.format = form.cleaned_data.get("format", data_object.format)
            data_object.data_type = form.cleaned_data.get("data_type", data_object.data_type)
            data_object.widget_type = form.cleaned_data.get("widget_type", data_object.widget_type)

            if (data_object.format == data_object.FORMAT_CHOICE_JSON) and (not data_object.key):
                form.add_error(None, "Key required for json data types")
                return render(request, self.template_name, self.context)

            data_object.save()
            return HttpResponse(status=201)
        else:
            form.add_error(None, "Error")
            return self.render_template(request)


"""
Ajax queries
"""
class QueryDataObjectsView(ViewsMixin, View):
    def __init__(self):
        super().__init__()
        self.set_template_name("dashboard/partials/ajax/dataobjects.html")

    def get(self, request, *args, **kwargs):
        self.user = get_user(request)
        if not self.user.is_authenticated:
            return HttpResponse(status=403)

        self.clear_context()
        topic = self.get_topic(kwargs["topic_id"])
        project = self.get_project(topic.project.pk)

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            t = pool.submit(
                db_utils.get_data_objects, project, topic
            )

            values_list = t.result()

        if values_list:
            data_details = list()
            for value_obj in values_list:
                data_detail = dict()
                data_detail["timestamp"] = datetime.datetime.fromtimestamp(float(value_obj["timestamp"]))
                for key, value in value_obj["value"].items():
                    data_object = get_object_or_404(DataObject, pk=key)
                    data_detail["model"] = data_object
                    data_detail["value"] = value
                    data_details.append(data_detail)

            self.add_context_data("data_details", data_details)

        return self.render_template(request)


class QueryDataObjectValues(ViewsMixin, View):
    def __init__(self):
        super().__init__()
        self.set_template_name("dashboard/partials/data_values_container.html")

    def get(self, request, *args, **kwargs):
        self.user = get_user(request)
        if not self.user.is_authenticated:
            return HttpResponse(status=403)

        self.clear_context()
        data_object = self.get_data_object(kwargs["dataobject_id"])
        topic = self.get_topic(data_object.topic.pk)
        project = self.get_project(topic.project.pk)
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            fut = pool.submit(
                db_utils.get_data_objects, project, topic
            )

            values_list = fut.result()

        if values_list:
            x_values = list()
            y_values = list()
            data_details = list()
            for value_obj in values_list:
                data_detail = dict()
                data_detail["timestamp"] = datetime.datetime.fromtimestamp(float(value_obj["timestamp"]))
                for key, value in value_obj["value"].items():
                    if int(key) != data_object.pk:
                        continue
                    data_detail["data_object"] = data_object
                    data_detail["value"] = value
                    data_details.append(data_detail)
                    x_values.append(data_detail["timestamp"])
                    y_values.append(value)

            plot = BokehPlot(x_list=x_values[:30], y_list=y_values[:30])
            if data_object.widget_type == DataObject.WIDGET_TYPE_LINE:
                plot.plot_timeseries()
                bokeh_script, bokeh_div = plot.get_components()
            elif data_object.widget_type == DataObject.WIDGET_TYPE_SCATTER:
                plot.scatter_plot("Scatter Plot")
                bokeh_script, bokeh_div = plot.get_components()
            elif data_object.widget_type == DataObject.WIDGET_TYPE_STATUS:
                plot.plot_timeseries()
                bokeh_script, bokeh_div = plot.get_components()
            else:
                bokeh_script, bokeh_div = plot.get_components()

            self.add_context_data("data_object", data_object)
            self.add_context_data("data_list", data_details[:30])
            self.add_context_data("bokeh_script", bokeh_script)
            self.add_context_data("bokeh_div", bokeh_div)

        return self.render_template(request)


class DownloadView(ViewsMixin, View):
    def __init__(self):
        super().__init__()

    def get(self, request, *args, **kwargs):
        dataobject = self.get_data_object(kwargs["dataobject_id"])
        topic = self.get_topic(dataobject.topic.pk)
        project = self.get_project(topic.project.pk)
        entries_num = 500

        aggregation = [
            {"$match": {
                "$and": [{"topic": topic.pk}, {"date": datetime.datetime.utcnow().toordinal()}]
            }},
            {"$sort": {"values.timestamp": pymongo.DESCENDING}},
            {"$limit": entries_num},
            {"$project": {"_id": 0, "values.timestamp": 1, f"values.value.{dataobject.pk}": 1}},
        ]

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            fut = pool.submit(
                db_utils.get_data_objects_by_aggregation, project, aggregation
            )

            cursor = fut.result()

        if not cursor:
            return HttpResponse(status=500)

        csv_rows = list()
        for obj in cursor:
            values = obj["values"]
            for elem in values:
                val_obj = elem["value"]
                val = val_obj.get(f"{dataobject.id}", None)
                if not val:
                    continue

                obj_time = datetime.datetime.fromtimestamp(elem["timestamp"])
                csv_row = (
                    f"{obj_time}", f"{val}"
                )
                csv_rows.append(csv_row)

        csv_writer_buffer = utils.CSVFileRowEcho()
        csv_writer = csv.writer(csv_writer_buffer)
        return StreamingHttpResponse(
            (csv_writer.writerow(row) for row in csv_rows),
            content_type="text/csv",
            headers={"Content-Disposition": "attachment; filename={}_{}".format(
                dataobject.id, datetime.datetime.utcnow().toordinal())
            }
        )


class RefreshConnectionsView(ViewsMixin, View):
    def __init__(self):
        super().__init__()
        self.set_template_name("dashboard/index/include/index_content.html")
        self.set_required_permissions([
            "dashboard.is_owner",
            "dashboard.can_view",
            "dashboard.can_delete",
        ])

    def get(self, request, *args, **kwargs):
        self.user = get_user(request)
        projects = self.get_projects()
        for project in projects:
            _client = mqtt_client_manager.get_client(project.pk)
            if not _client:
                mqtt_client_manager.add_client(
                    client_id=project.pk,
                    host=project.host,
                    port=project.port
                )

        mqtt_client_manager.refresh_clients()
        self.clear_context()
        self.add_context_data("project_list", self.get_projects_param_list())
        return self.render_template(request)


class CheckConnectionView(View):
    connected_template = "dashboard/partials/ajax/project_connected.html"
    disconnected_template = "dashboard/partials/ajax/project_disconnected.html"

    def get(self, request, *args, **kwargs):
        try:
            project_id = kwargs["project_id"]
        except KeyError:
            logging.error("Key error")
            return HttpResponse(status=404)

        mqtt_client = mqtt_client_manager.get_client(int(project_id))
        if not mqtt_client:
            return HttpResponse(status=404)

        if mqtt_client.connected:
            return render(request, self.connected_template)
        else:
            return render(request, self.disconnected_template)
