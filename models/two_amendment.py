from odoo import api, fields, models, _


class TwoAmendment(models.Model):
    _name = 'top.two.amendment'
    _description = 'Transport Work Order Post-Commencement Amendment'
    _inherit = ['mail.thread']
    _order = 'amendment_date desc, id desc'

    two_id = fields.Many2one(
        'top.fleet.trip',
        string='Transport Work Order (TWO)',
        required=True,
        ondelete='cascade',
        index=True,
    )
    amendment_date = fields.Datetime(
        string='Amendment Timestamp',
        default=fields.Datetime.now,
        required=True,
    )
    delta_km = fields.Float(
        string='Incremental Distance (Δ KM)',
        required=True,
        default=0.0,
        help='Additional distance beyond the originally approved operational plan.',
    )
    delta_fuel = fields.Float(
        string='Incremental Fuel Required (Δ L)',
        required=True,
        default=0.0,
        help='Additional fuel authorized to complete the modified legs.',
    )
    reason = fields.Text(
        string='Amendment Justification',
        required=True,
    )
    loading_status = fields.Selection([
        ('pickup', 'Additional En-Route Pickup'),
        ('dropoff', 'Additional En-Route Dropoff'),
        ('reroute', 'Road Closure / Detour Reroute'),
        ('subtrip', 'Site Local Sub-Trip Extension'),
    ], string='Amendment Category', default='pickup', required=True)

    requested_by_id = fields.Many2one(
        'res.users',
        string='Requested By',
        default=lambda self: self.env.user,
    )
    approved_by_id = fields.Many2one(
        'res.users',
        string='Approved By Fleet Manager',
        tracking=True,
    )
    state = fields.Selection([
        ('draft', 'Draft'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ], string='Status', default='draft', tracking=True)

    def action_approve(self):
        for rec in self:
            rec.state = 'approved'
            rec.approved_by_id = self.env.user
            # Update parent trip / TWO
            if rec.two_id:
                rec.two_id.enroute_distance_added += rec.delta_km
                rec.two_id.state = 'in_transit'
