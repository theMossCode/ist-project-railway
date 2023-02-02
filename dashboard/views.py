import asyncio
import concurrent.futures
import csv
import logging
import datetime
import time

from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse, StreamingHttpResponse
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user
from django.utils.decorators import method_decorator

from guardian.shortcuts import assign_perm, get_perms, get_objects_for_user

from asgiref.sync import async_to_sync, sync_to_async
from channels.layers import get_channel_layer

from .forms import NewProjectForm, NewTopicForm, NewDataObjectForm
from .models import Project, Topic, DataObject
from .mongodb import get_db_name, db_utils

from django.views.generic import TemplateView
from django.views import View

from .bokeh_utils import Plot

from .mqtt import mqtt_client_manager

channel_layer = get_channel_layer()
detail_decorators = [login_required(login_url="authentication:login")]

@method_decorator(detail_decorators, name="dispatch")
class IndexView(TemplateView):
    template_name = "dashboard/index/index.html"
    project_required_permissions = [
        "dashboard.is_owner",
        "dashboard.can_view",
        "dashboard.can_delete",
    ]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = get_user(self.request)
        logging.debug(user)
        context["user"] = user
        context["project_list"] = self.get_projects_list(user)
        return context

    def get_projects_list(self, user):
        try:
            projects_list = list()
            projects = get_objects_for_user(user, self.project_required_permissions, any_perm=True)
            logging.debug(projects)
            for project in projects:
                topics = Topic.objects.filter(project=project)
                projects_entry = {
                    "project": project,
                    "topics": topics
                }
                projects_list.append(projects_entry)

            return projects_list
        except Exception as e:
            logging.debug(e)
            return list()


@method_decorator(detail_decorators, name="dispatch")
class DetailProjectView(TemplateView):
    template_name = "dashboard/detail/project.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data()
        try:
            context["project"] = Project.objects.get(pk=kwargs["project_id"])
            context["topics"] = Topic.objects.filter(project=context["project"])
            return context
        except Exception as e:
            return dict()


@method_decorator(detail_decorators, name="dispatch")
class DetailTopicView(TemplateView):
    template_name = "dashboard/detail/topic.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        try:
            context["topic"] = Topic.objects.get(pk=kwargs["topic_id"])
            context["data_objects"] = DataObject.objects.filter(topic=context["topic"])
            logging.debug(context)
            return context
        except Exception as e:
            logging.debug(e)
            return None


@method_decorator(detail_decorators, name="dispatch")
class DetailDataObjectView(TemplateView):
    template_name = "dashboard/detail/dataobject.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        try:
            context["dataobject"] = DataObject.objects.get(pk=kwargs["dataobject_id"])
            context["topic"] = Topic.objects.get(pk=context["dataobject"].topic.pk)
            context["project"] = Project.objects.get(pk=context["topic"].project.pk)
            context["data_duration"] = 30
            logging.debug(context)
            return context
        except Exception as e:
            logging.debug(e)
            return None


"""
New Views
"""


class NewProjectView(View):
    form_class = NewProjectForm
    template = "dashboard/modals/new_project.html"

    def start_mqtt_client(self, project):
        mqtt_client_manager.add_client(
            client_id=project.pk,
            host=project.host,
            port=project.port,
        )
        mqtt_client_manager.connect_client(project.pk)
        mqtt_client_manager.start_client(project.pk)

    def get(self, request, *args, **kwargs):
        initial = {"mqtt_port": 1883}
        user = get_user(request)
        if not user.is_authenticated:
            return HttpResponse(status=403)

        form = self.form_class(initial=initial)
        return render(request, self.template, {"form": form})

    def post(self, request, *args, **kwargs):
        user = get_user(request)
        if not user.is_authenticated:
            return HttpResponse(status=403)

        form = self.form_class(request.POST)
        project = None
        if form.is_valid():
            project = Project(
                name=form.cleaned_data["name"],
                description=form.cleaned_data["desc"],
                host=form.cleaned_data["mqtt_host"],
                port=form.cleaned_data["mqtt_port"],
                username=form.cleaned_data["mqtt_username"],
                password=form.cleaned_data["mqtt_password"],
                db_name=get_db_name(user),
            )

            try:
                project.save()
                assign_perm("is_owner", user, project)
                mqtt_client_manager.add_client(
                    client_id=project.pk,
                    host=project.host,
                    port=project.port,
                    userdata=None
                )
                self.start_mqtt_client(project)
                return HttpResponse(status=201)
            except Exception as e:
                logging.error(e)
                if project:
                    project.delete()

                form.add_error(None, "Unknown error!!")
                return render(request, self.template, {"form": form})
        else:
            form.add_error(None, "Form not valid. Please review form and update.")
            return render(request, self.template, {"form": form})


class NewTopicView(View):
    qos_choices = Topic.QOS_CHOICES
    form_class = NewTopicForm
    template = "dashboard/modals/new_topic.html"

    def subscribe_mqtt_topic(self, project, topic):
        _client = mqtt_client_manager.get_client(project.pk)
        if not _client:
            logging.debug("Not valid client")
            return False

        logging.debug(_client.host)
        return async_to_sync(_client.subscribe_topic)(
            topic=topic.path,
            qos=topic.qos
        )

    def get(self, request, *args, **kwargs):
        user = get_user(request)
        if not user.is_authenticated:
            return HttpResponse(status=403)

        project = get_object_or_404(Project, pk=kwargs["project_id"])
        initial = {
            "project_id": project.pk,
        }
        form = self.form_class(initial=initial)
        context = {
            "form": form,
            "project": project,
            "qos_choices": self.qos_choices,
        }
        return render(request, self.template, context)

    def post(self, request, *args, **kwargs):
        user = get_user(request)
        if not user.is_authenticated:
            return HttpResponse(status=403)

        project = get_object_or_404(Project, pk=kwargs["project_id"])
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

            try:
                res = self.subscribe_mqtt_topic(project, topic)
                if not res:
                    raise RuntimeError("Could not subscribe")
                topic.save()
                return HttpResponse(status=201)
            except Exception as e:
                logging.exception(e)
                form.add_error(None, "Unknown error occured!")
                if topic.id:
                    topic.delete()

                context = {
                    "form": form,
                    "project": project,
                    "qos_choices": self.qos_choices,
                }
                return render(request, self.template, context)
        else:
            logging.debug(form.errors)
            form.add_error(None, "Invalid form!")
            context = {
                "form": form,
                "project": project,
                "qos_choices": self.qos_choices,
            }
            return render(request, self.template, context)


class NewDataObject(View):
    template_name = "dashboard/modals/new_dataobject.html"
    form_class = NewDataObjectForm
    context = {
        "format_choices": DataObject.FORMAT_CHOICES,
        "data_types": DataObject.DATA_TYPE_CHOICES,
    }

    def get(self, request, *args, **kwargs):
        topic = Topic.objects.get(pk=kwargs["topic_id"])
        form = self.form_class()
        self.context["topic"] = topic
        self.context["form"] = form
        return render(request, self.template_name, context=self.context)

    def post(self, request, *args, **kwargs):
        dataobject = None
        topic = Topic.objects.get(pk=kwargs["topic_id"])
        form = self.form_class(request.POST)
        self.context["topic"] = topic
        self.context["form"] = form

        if form.is_valid():
            if (not form.cleaned_data["key"]) and (form.cleaned_data["format"] == DataObject.FORMAT_CHOICE_JSON):
                form.add_error(None, "Key required for JSON types")
                return render(request, self.template_name, context=self.context)

            dataobject = DataObject(
                name=form.cleaned_data["name"],
                description=form.cleaned_data["desc"],
                format=form.cleaned_data["format"],
                data_type=form.cleaned_data["data_type"],
                path=form.cleaned_data["path"],
                key=form.cleaned_data["key"],
                topic=topic
            )
            try:
                dataobject.save()
                return HttpResponse(status=201)
            except Exception as e:
                logging.debug(e)
                if dataobject:
                    dataobject.delete()

                form.add_error(None, "Unknown error occurred!")
                return render(request, self.template_name, context=self.context)
        else:
            form.add_error(None, "Form invalid!")
            return render(request, self.template_name, context=self.context)


"""
Delete
"""


class DeleteViewBase(View):
    user_permissions = None
    required_permissions = [
        "dashboard.is_owner",
        "dashboard.can_delete",
    ]


class DeleteProjectView(DeleteViewBase):
    user_permissions = None
    template_name = "dashboard/index/include/index_content.html"

    def get(self, request, *args, **kwargs):
        user = get_user(request)
        project = get_object_or_404(Project, pk=kwargs["project_id"])

        self.user_permissions = get_perms(user, project)
        if (("is_owner" not in self.user_permissions)
                and ("can_delete" not in self.user_permissions)):
            return HttpResponse(status=403)

        # if not mongodb_utils.delete_project_collection(project):
        #     return HttpResponse(status=500)

        # Disconnect broker
        mqtt_client_manager.delete_client(project.pk)

        project.delete()
        return self.render_template(request)

    def render_template(self, request):
        user = get_user(request)
        project_list = list()
        for _project in get_objects_for_user(user, self.required_permissions, any_perm=True):
            _topics = Topic.objects.filter(project=_project)
            project_info = {
                "project": _project,
                "topics": _topics,
            }
            project_list.append(project_info)

        context = {
            "project_list": project_list,
        }
        return render(request, self.template_name, context=context)


class DeleteTopicView(DeleteViewBase):
    template_name = "dashboard/detail/include/project_content.html"

    def get(self, request, *args, **kwargs):
        user = get_user(request)
        topic = get_object_or_404(Topic, pk=kwargs["topic_id"])
        project = get_object_or_404(Project, pk=topic.project.pk)

        # if not mongodb_utils.delete_topic_documents(project, topic):
        #     return HttpResponse(status=500)

        self.unsubscribe_mqtt_topic(project, topic)
        topic.delete()
        return self.render_template(request, project)

    def render_template(self, request, project):
        context = {
            "project": project,
            "topics": Topic.objects.filter(project=project),
        }

        return render(request, self.template_name, context=context)

    def unsubscribe_mqtt_topic(self, project, topic):
        async_to_sync(channel_layer.send)(
            "mqtt",
            {
                "type": "client.unsubscribe.topic",
                "project_id": project.pk,
                "topic_path": topic.path,
            }
        )


class DeleteDataObject(DeleteViewBase):
    template_name = "dashboard/detail/include/topic_content.html"

    def get(self, request, *args, **kwargs):
        user = get_user(request)
        dataobject = get_object_or_404(DataObject, pk=kwargs["dataobject_id"])
        topic = get_object_or_404(Topic, pk=dataobject.topic.pk)
        project = get_object_or_404(Project, pk=topic.project.pk)
        # res = mongodb_utils.delete_dataobject(project, topic, dataobject)
        # if not mongodb_utils.delete_dataobject(project, topic, dataobject):
        #     logging.debug("MongoDB delete error!")
        #     return HttpResponse(status=500)

        dataobject.delete()
        return self.render_template(request, topic)

    def render_template(self, request, topic):
        context = {
            "topic": topic,
            "data_objects": DataObject.objects.filter(topic=topic),
        }

        return render(request, self.template_name, context=context)


class EditDataObjectView(View):
    form_class = NewDataObjectForm
    template_name = "dashboard/modals/edit_dataobject.html"
    context = {
        "format_choices": DataObject.FORMAT_CHOICES,
        "data_types": DataObject.DATA_TYPE_CHOICES,
    }

    def get(self, request, *args, **kwargs):
        dataobject = get_object_or_404(DataObject, pk=kwargs["dataobject_id"])
        topic = get_object_or_404(Topic, pk=dataobject.topic.pk)
        # project = get_object_or_404(Project, pk=topic.project.pk)

        initial = {
            "name": dataobject.name,
            "desc": dataobject.description,
            "data_type": dataobject.data_type,
            "path": dataobject.path,
            "format": dataobject.format,
            "key": dataobject.key,
        }

        form = self.form_class(initial)
        self.context["form"] = form
        self.context["dataobject"] = dataobject
        return render(request, self.template_name, self.context)

    def post(self, request, *args, **kwargs):
        dataobject = DataObject.objects.get(pk=kwargs["dataobject_id"])

        form = self.form_class(request.POST)
        self.context["form"] = form
        self.context["dataobject"] = dataobject
        if not form.has_changed():
            return HttpResponse(status=201)
        elif form.is_valid():
            dataobject.name = form.cleaned_data.get("name", dataobject.name)
            dataobject.description = form.cleaned_data.get("desc", dataobject.description)
            dataobject.path = form.cleaned_data.get("path", dataobject.path)
            dataobject.key = form.cleaned_data.get("key", dataobject.key)
            dataobject.format = form.cleaned_data.get("format", dataobject.format)
            dataobject.data_type = form.cleaned_data.get("data_type", dataobject.data_type)

            if (dataobject.format == dataobject.FORMAT_CHOICE_JSON) and (not dataobject.key):
                form.add_error(None, "Key required for json data types")
                return render(request, self.template_name, self.context)

            dataobject.save()
            return HttpResponse(status=201)
        else:
            form.add_error(None, "Error")
            return render(request, self.template_name, self.context)

"""
Ajax queries
"""


class QueryDataObjectsView(View):
    template_name = "dashboard/partials/ajax/dataobjects.html"

    def get_data_objects(self, project, topic):
        loop = asyncio.new_event_loop()
        future = loop.create_future()
        loop.run_until_complete(
            async_mongodb.get_data_objects(project, topic)
        )
        loop.close()

    def get(self, request, *args, **kwargs):
        user = get_user(request)
        if not user.is_authenticated:
            return HttpResponse(status=403)

        logging.debug("Query dataobjects")
        topic = get_object_or_404(Topic, pk=kwargs["topic_id"])
        project = get_object_or_404(Project, pk=topic.project.pk)

        # values_list = mongo_db_loop.run_until_complete(
        #     async_mongodb.get_data_objects(project, topic)
        # )
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

            context = {
                "data_details": data_details
            }
        else:
            context = None

        return render(request, self.template_name, context)

    def sort_func(self, e):
        return e["timestamp"]


class QueryDataObjectValues(View):
    template_name = "dashboard/partials/ajax/dataobject_values.html"

    def get(self, request, *args, **kwargs):
        user = get_user(request)
        if not user.is_authenticated:
            return HttpResponse(status=403)

        context = dict()

        data_object = get_object_or_404(DataObject, pk=kwargs["dataobject_id"])
        topic = get_object_or_404(Topic, pk=data_object.topic.pk)
        project = get_object_or_404(Project, pk=topic.project.pk)
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            fut = pool.submit(
                db_utils.get_data_objects, project, topic
            )

            values_list = fut.result()

        if values_list:
            plot_x = list()
            plot_y = list()
            data_details = list()
            for value_obj in values_list:
                data_detail = dict()
                data_detail["timestamp"] = datetime.datetime.fromtimestamp(float(value_obj["timestamp"]))
                logging.debug(value_obj)
                for key, value in value_obj["value"].items():
                    if int(key) != data_object.pk:
                        continue
                    data_detail["data_object"] = data_object
                    data_detail["value"] = value
                    data_details.append(data_detail)
                    plot_x.append(data_detail["timestamp"])
                    plot_y.append(value)

            plot = Plot(x_list=plot_x, y_list=plot_y)
            plot.plot_timeseries()
            bokeh_script, bokeh_div = plot.get_components()
            context = {
                "data_list": data_details,
                "bokeh_script": bokeh_script,
                "bokeh_div": bokeh_div,
            }
        else:
            context = None

        return render(request, self.template_name, context)


class DownloadView(View):
    def get(self, request, *args, **kwargs):
        return HttpResponse(status=404)
        # dataobject = DataObject.objects.get(pk=kwargs["dataobject_id"])
        # topic = Topic.objects.get(pk=dataobject.topic.pk)
        # project = Topic.objects.get(pk=topic.project.pk)
        # start_time = datetime.datetime.utcnow() - datetime.timedelta(hours=24)
        # entries_num = 500
        #
        # aggregation = [
        #     {"$match": {"data.{}".format(dataobject.pk): {"$exists": True}}},
        #     {"$limit": entries_num},
        # ]
        #
        # dataobjects_list = list(
        #     mongodb_utils.get_data_objects(project, topic, aggregation=aggregation)
        # )
        #
        # csv_rows = (
        #     ["{}".format(data["time"]), "{}".format(data["data"][str(dataobject.pk)])] for data in dataobjects_list
        # )
        # csv_writer_buffer = utils.CSVFileRowEcho()
        # csv_writer = csv.writer(csv_writer_buffer)
        # return StreamingHttpResponse(
        #     (csv_writer.writerow(row) for row in csv_rows),
        #     content_type="text/csv",
        #     headers={"Content-Disposition": "attachment; filename={}_{}".format(
        #         dataobject.id, datetime.datetime.utcnow().toordinal())
        #     }
        # )


class RefreshConnectionsView(View):
    template_name = "dashboard/index/include/index_content.html"
    def send_mqtt_consumer_refresh(self):
        logging.debug("Refresh client connections")
        mqtt_client_manager.refresh_clients()

    def get(self, request, *args, **kwargs):
        projects = Project.objects.all()
        for project in projects:
            _client = mqtt_client_manager.get_client(project.pk)
            if not _client:
                logging.debug(f"Add client {project.pk}")
                mqtt_client_manager.add_client(
                    client_id=project.pk,
                    host=project.host,
                    port=project.port
                )
        self.send_mqtt_consumer_refresh()
        projects = Project.objects.all()[:10]
        project_list = list()
        for project in projects:
            topics = Topic.objects.filter(project=project)
            project_info = {
                "project": project,
                "topics": topics,
            }
            project_list.append(project_info)

        return render(request, self.template_name, {"project_list": project_list})
