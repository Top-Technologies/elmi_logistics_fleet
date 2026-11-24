# -*- coding: utf-8 -*-
import json
import logging
import math
import re
import urllib.parse
import urllib.request
from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class LogisticsLocation(models.Model):
    _name = 'top.logistics.location'
    _description = 'Predefined Logistics Location'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name asc'

    name = fields.Char(
        string='Location Name',
        required=True,
        tracking=True,
        index=True,
    )
    code = fields.Char(
        string='Location Code',
        copy=False,
        tracking=True,
        index=True,
        help='Unique identifier e.g. HQ-ADD, BR-JIM, WHS-ADA',
    )
    location_type = fields.Selection([
        ('depot', 'Main Depot / Terminal'),
        ('branch', 'Branch Office'),
        ('farm', 'Farm Estate / Plantation'),
        ('warehouse', 'Warehouse / Hub'),
        ('project_site', 'Project / Field Site'),
        ('client', 'Client / Vendor Location'),
        ('transit', 'Transit / Fuel Stop'),
        ('other', 'Other Location'),
    ], string='Location Type', default='depot', required=True, tracking=True)

    google_maps_query = fields.Char(
        string='Google Maps Search / URL / Coordinates',
        help='Search place name, paste Google Maps URL or enter Lat, Lng coordinates (e.g. 9.0123, 38.7456)'
    )
    formatted_address = fields.Char(
        string='Formatted Map Address',
        readonly=True,
        help='Full geocoded address returned by map service.'
    )

    contact_person = fields.Char(string='Contact Person')
    phone = fields.Char(string='Contact Phone')
    street = fields.Char(string='Street / Area Address')
    city = fields.Char(string='City / Town', default='ADDIS ABABA')
    subcity = fields.Char(string='Sub-City / KK (Kifle Ketema)', help='e.g. KIRKOS, KOLFE KERANEO')
    woreda = fields.Char(string='Woreda', help='e.g. 04, 03')
    kebele = fields.Char(string='Kebele', help='e.g. KOLFE KERANEO')
    state_name = fields.Char(string='State / Region Name', default='ADDIS ABABA')
    state_id = fields.Many2one('res.country.state', string='Region / State')
    country_id = fields.Many2one(
        'res.country',
        string='Country',
        default=lambda self: self.env.ref('base.et', raise_if_not_found=False),
    )
    latitude = fields.Float(string='Latitude', digits=(10, 6))
    longitude = fields.Float(string='Longitude', digits=(10, 6))
    geofence_id = fields.Many2one(
        'top.gps.geofence',
        string='Linked GPS Geofence',
        help='Optional GPS geofence linked to this location for automated arrival/departure detection.',
    )
    active = fields.Boolean(string='Active', default=True, tracking=True)
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True,
    )
    notes = fields.Text(string='Internal Notes / Instructions')

    def name_get(self):
        result = []
        for rec in self:
            name_part = rec.name or ''
            label = f"[{rec.code}] {name_part}" if rec.code else name_part
            if rec.city and label:
                label += f" ({rec.city})"
            elif rec.city:
                label = rec.city
            result.append((rec.id, label or _("New Location")))
        return result

    @api.depends('name', 'code', 'city')
    def _compute_display_name(self):
        for rec in self:
            name_part = rec.name or ''
            label = f"[{rec.code}] {name_part}" if rec.code else name_part
            if rec.city and label:
                label += f" ({rec.city})"
            elif rec.city:
                label = rec.city
            rec.display_name = label or _("New Location")

    @api.onchange('google_maps_query')
    def _onchange_google_maps_query(self):
        if self.google_maps_query:
            self._parse_and_apply_coordinates(self.google_maps_query)

    def _parse_and_apply_coordinates(self, text):
        """Extracts latitude and longitude from Google Maps URLs or direct numeric coordinates."""
        if not text:
            return False
        # 1. Google Maps standard @lat,lon,zoom
        m = re.search(r'@([-+]?\d{1,2}\.\d+),([-+]?\d{1,3}\.\d+)', text)
        if not m:
            # 2. Query param ?q=lat,lon or ll=lat,lon
            m = re.search(r'[?&](?:q|ll)=([-+]?\d{1,2}\.\d+),([-+]?\d{1,3}\.\d+)', text)
        if not m:
            # 3. Direct raw coordinates: "9.0123, 38.7456"
            m = re.search(r'^\s*([-+]?\d{1,2}\.\d+)[,\s]+([-+]?\d{1,3}\.\d+)\s*$', text.strip())
        if not m:
            # 4. Embedded decimal coordinates in string
            m = re.search(r'([-+]?\d{1,2}\.\d{3,})[,\s]+([-+]?\d{1,3}\.\d{3,})', text)

        if m:
            self.latitude = round(float(m.group(1)), 6)
            self.longitude = round(float(m.group(2)), 6)
            return True
        return False

    def action_fetch_google_location(self):
        """Fetches GPS coordinates and address from Google Maps / OpenStreetMap Nominatim."""
        self.ensure_one()
        query = (self.google_maps_query or '').strip()

        # Check if direct coordinates or Google Maps link are provided
        if query and self._parse_and_apply_coordinates(query):
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _("Coordinates Extracted"),
                    'message': _("GPS Coordinates extracted: %s, %s") % (self.latitude, self.longitude),
                    'type': 'success',
                    'sticky': False,
                }
            }

        # Build address search query
        search_terms = []
        if query:
            search_terms.append(query)
        else:
            if self.name:
                search_terms.append(self.name)
            if self.street:
                search_terms.append(self.street)
            if self.subcity:
                search_terms.append(self.subcity)
            if self.city:
                search_terms.append(self.city)
            if self.country_id:
                search_terms.append(self.country_id.name)

        if not search_terms:
            raise UserError(_("Please enter a location name, address, or Google Maps query to locate."))

        full_query = ", ".join(search_terms)

        try:
            url = f"https://nominatim.openstreetmap.org/search?q={urllib.parse.quote(full_query)}&format=json&limit=1&addressdetails=1"
            req = urllib.request.Request(
                url,
                headers={'User-Agent': 'TopLogisticsFleet/1.0 (Odoo Logistics Management)'}
            )
            with urllib.request.urlopen(req, timeout=4) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode())
                    if data and len(data) > 0:
                        top_res = data[0]
                        self.latitude = round(float(top_res.get('lat', 0.0)), 6)
                        self.longitude = round(float(top_res.get('lon', 0.0)), 6)
                        self.formatted_address = top_res.get('display_name')

                        addr = top_res.get('address', {})
                        if not self.city and (addr.get('city') or addr.get('town') or addr.get('county')):
                            self.city = addr.get('city') or addr.get('town') or addr.get('county')
                        if not self.street and (addr.get('road') or addr.get('suburb')):
                            self.street = addr.get('road') or addr.get('suburb')

                        return {
                            'type': 'ir.actions.client',
                            'tag': 'display_notification',
                            'params': {
                                'title': _("Location Found!"),
                                'message': _("Located: %s\nLat: %s, Lon: %s") % (self.formatted_address, self.latitude, self.longitude),
                                'type': 'success',
                                'sticky': False,
                            }
                        }
        except Exception as e:
            _logger.warning("Geocoding failed for '%s': %s", full_query, str(e))

        raise UserError(_("Could not locate '%s' online. You can enter the coordinates directly (e.g. 9.0123, 38.7456) or paste a Google Maps link into the search box.") % full_query)

    def action_open_google_maps(self):
        """Opens the location in Google Maps in a new tab."""
        self.ensure_one()
        if self.latitude and self.longitude:
            url = f"https://www.google.com/maps?q={self.latitude},{self.longitude}"
        else:
            query = f"{self.name}, {self.city or ''}, {self.country_id.name if self.country_id else ''}"
            url = f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote(query)}"
        return {
            'type': 'ir.actions.act_url',
            'url': url,
            'target': 'new',
        }

    @api.model
    def calculate_distance_km(cls, lat1, lon1, lat2, lon2):
        """Calculates road-estimated distance between two points in km."""
        if not (lat1 and lon1 and lat2 and lon2):
            return 0.0
        if abs(lat1 - lat2) < 0.0001 and abs(lon1 - lon2) < 0.0001:
            return 0.0

        # Haversine formula
        R = 6371.0 # Earth radius in km
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = (math.sin(dlat / 2.0) ** 2 +
             math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
             math.sin(dlon / 2.0) ** 2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        direct_dist = R * c

        # Road detour coefficient (1.28x for standard road network winding factor)
        road_distance = direct_dist * 1.28
        return round(road_distance, 1)

    @api.model
    def calculate_route_metrics(cls, points):
        """
        Calculates cumulative distance (km) and estimated duration (hours) across a list of (lat, lon) coordinates.
        points: list of tuples [(lat1, lon1), (lat2, lon2), ...]
        """
        valid_points = [(lat, lon) for lat, lon in points if (lat and lon)]
        if len(valid_points) < 2:
            return {'distance_km': 0.0, 'duration_hours': 0.0}

        total_km = 0.0
        for i in range(len(valid_points) - 1):
            p1 = valid_points[i]
            p2 = valid_points[i + 1]
            total_km += cls.calculate_distance_km(p1[0], p1[1], p2[0], p2[1])

        # Estimated duration assuming average fleet speed of 55 km/h + 15 min buffer per stop
        stops_count = max(0, len(valid_points) - 2)
        transit_hours = (total_km / 55.0) if total_km > 0 else 0.0
        buffer_hours = stops_count * 0.25 # 15 mins dwell per stop
        total_hours = round(transit_hours + buffer_hours, 1)

        return {
            'distance_km': round(total_km, 1),
            'duration_hours': total_hours,
        }
