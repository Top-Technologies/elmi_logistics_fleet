from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError


class FleetMeterReading(models.Model):
    _name = 'fleet.meter.reading'
    _description = 'Fleet Meter Reading Log (Hours and KM)'
    _inherit = ['mail.thread']
    _order = 'reading_date desc, id desc'

    vehicle_id = fields.Many2one(
        'fleet.vehicle',
        string='Vehicle / Asset',
        required=True,
        index=True,
        tracking=True,
    )
    meter_type = fields.Selection([
        ('km', 'Kilometers (KM)'),
        ('hours', 'Operating Hours (Hrs)'),
    ], string='Meter Type', required=True, default='km', tracking=True)

    value = fields.Float(
        string='Reading Value',
        required=True,
        tracking=True,
    )
    reading_date = fields.Datetime(
        string='Reading Date and Time',
        default=fields.Datetime.now,
        required=True,
        tracking=True,
    )
    source = fields.Selection([
        ('manual', 'Manual Entry'),
        ('import', 'Site Excel Log Import'),
        ('dispatch', 'Gate Dispatch / Return'),
        ('fuel', 'Fuel Issue Log'),
        ('gps', 'GPS Telematics Ping'),
    ], string='Reading Source', default='manual', required=True, tracking=True)

    task_description = fields.Char(string='Operating Task / Activity')
    operator_id = fields.Many2one('hr.employee', string='Operator / Driver')
    site_location_id = fields.Many2one('top.logistics.location', string='Site Location')

    # Manager Monotonic Override
    is_override = fields.Boolean(
        string='Manager Monotonic Override',
        default=False,
        tracking=True,
        help='Checked if this reading was accepted below the previous reading by authorized manager override.',
    )
    override_by_id = fields.Many2one(
        'res.users',
        string='Override Approved By',
        tracking=True,
    )
    override_reason = fields.Text(string='Override Justification')

    @api.constrains('vehicle_id', 'meter_type', 'value', 'reading_date', 'is_override')
    def _check_monotonic_reading(self):
        for rec in self:
            if rec.is_override:
                continue
            # Search for latest reading of the same vehicle and meter_type before or equal to this date
            prev_reading = self.search([
                ('vehicle_id', '=', rec.vehicle_id.id),
                ('meter_type', '=', rec.meter_type),
                ('reading_date', '<=', rec.reading_date),
                ('id', '!=', rec.id),
            ], order='reading_date desc, id desc', limit=1)

            if prev_reading and rec.value < prev_reading.value:
                unit = 'KM' if rec.meter_type == 'km' else 'Hours'
                raise ValidationError(_(
                    "Monotonic Reading Violation for %(vehicle)s: New reading (%(val).1f %(unit)s) is lower than "
                    "the previously recorded reading (%(prev).1f %(unit)s on %(date)s).\n"
                    "If a meter replacement or rollback occurred, this entry requires an explicit Fleet Manager Override."
                ) % {
                    'vehicle': rec.vehicle_id.display_name,
                    'val': rec.value,
                    'unit': unit,
                    'prev': prev_reading.value,
                    'date': prev_reading.reading_date,
                })
