import cStringIO
import codecs
from datetime import datetime
from functools import update_wrapper
from django.contrib import admin
from django.http import HttpResponse
import csv
import re
import urllib

class UnicodeWriter:
    """
    A CSV writer which will write rows to CSV file "f",
    which is encoded in the given encoding.
    """

    def __init__(self, f, dialect=csv.excel, encoding="utf-8", **kwds):
        # Redirect output to a queue
        self.queue = cStringIO.StringIO()
        self.writer = csv.writer(self.queue, dialect=dialect, **kwds)
        self.stream = f
        self.encoder = codecs.getincrementalencoder(encoding)()

    def writerow(self, row):
        self.writer.writerow([s.encode("utf-8") for s in row])
        # Fetch UTF-8 output from the queue ...
        data = self.queue.getvalue()
        data = data.decode("utf-8")
        # ... and reencode it into the target encoding
        data = self.encoder.encode(data)
        # write to the target stream
        self.stream.write(data)
        # empty queue
        self.queue.truncate(0)

    def writerows(self, rows):
        for row in rows:
            self.writerow(row)

class CSVExportableAdmin(admin.ModelAdmin):
    csv_export_url = '~csv/'
    csv_export_dialect = 'excel'
    csv_follow_relations = []
    csv_export_fmtparam = {
       'delimiter': ',',
       'quotechar': '\\',
       'quoting': csv.QUOTE_MINIMAL,
    }
    csv_list_fields = False
    csv_encoding = "utf8"
    change_list_template = 'csvexport/change_list.html'
    
    def get_urls(self):
        from django.conf.urls.defaults import patterns, url

        def wrap(view):
            def wrapper(*args, **kwargs):
                return self.admin_site.admin_view(view)(*args, **kwargs)
            return update_wrapper(wrapper, view)

        info = self.model._meta.app_label, self.model._meta.module_name
        
        urlpatterns = patterns('',
            url(r'^%s$' % re.escape(self.csv_export_url),
                wrap(self.csv_export),
                name='%s_%s_csv_export' % info),
        )
        urlpatterns += super(CSVExportableAdmin, self).get_urls()
        return urlpatterns
    
    def csv_export(self, request):
        fields = self.get_csv_export_fields(request)
        headers = [self.csv_get_fieldname(f) for f in fields]
        
        from django.contrib.admin.views.main import ChangeList
        cl = ChangeList(request, self.model, self.list_display, self.list_display_links, self.list_filter,
            self.date_hierarchy, self.search_fields, self.list_select_related, self.list_per_page, self.list_editable, self)
        qs = cl.get_query_set()
        
        response = HttpResponse(mimetype='text/csv')
        response['Content-Disposition'] = 'attachment; filename=%s' % self.csv_get_export_filename(request)
        writer = UnicodeWriter(response, self.csv_export_dialect, encoding=self.csv_encoding, **self.csv_export_fmtparam)
        writer.writerow(headers)
        for row in qs:
            csvrow = [self.csv_resolve_field(row, f) for f in fields]
            writer.writerow(csvrow)    
        return response
        
    def get_csv_export_fields(self, request):
        """

            Return a sequence of tuples which should be included in the export.
        """
        
        if not self.csv_list_fields:

            fields = [f.name for f in self.model._meta.fields]
            for relation in self.csv_follow_relations:
                for field in self.model._meta.get_field_by_name(relation)[0].rel.to._meta.fields:
                    fields.append([relation, field.name])
            return fields
        
        fields_ = self.list_display
        fields = []
        for f in fields_:
            if f == 'action_checkbox':
                continue
            if f == '__unicode__':
                fields.append(f)
                continue
            if "__" in f:
                fields.append(tuple(f.split('__')))
            else:
                fields.append(f)
        return fields

    def csv_get_export_filename(self, request):
        ts = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        return '%s_%s_%s_export.csv' % (ts, self.model._meta.app_label, self.model._meta.module_name)

    def csv_resolve_field(self, row, fieldname):
        def internal():
            if isinstance(fieldname, basestring):
                return getattr(row, fieldname)
            else:
                obj = row
                for bit in fieldname:
                    obj = getattr(obj, bit)
                return obj

        obj = internal()
        try:
            obj = obj()
        except TypeError:
            pass
        if not isinstance(obj, basestring):
            obj = unicode(obj)
        return obj


    def csv_get_fieldname(self, field):
        if isinstance(field, basestring):
            return field
        return '.'.join(field)

    def csv_build_get_string(self, request):
        params = []
        for name in request.GET.iterkeys():
            for x in request.GET.getlist(name):
                params.append((name, x))

        return u"%s?%s" % (self.csv_export_url, urllib.urlencode(params))
        

    def changelist_view(self, request, extra_context=None):
        extra_context = {'csv_export_url': self.csv_build_get_string(request)}
        return super(CSVExportableAdmin, self).changelist_view(request, extra_context)