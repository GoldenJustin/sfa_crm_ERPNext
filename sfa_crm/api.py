import frappe
import json

def set_default_company(doc, method=None):
    if hasattr(doc, "company") and not doc.get("company"):
        company = (
            frappe.defaults.get_user_default("Company")
            or frappe.db.get_single_value("Global Defaults", "default_company")
            or frappe.db.get_value("Company", {}, "name")
        )
        if company:
            doc.company = company

@frappe.whitelist(allow_guest=True)
def sfa_login(usr, pwd):
    try:
        login_manager = frappe.auth.LoginManager()
        login_manager.authenticate(user=usr, pwd=pwd)
        login_manager.post_login()
    except frappe.exceptions.AuthenticationError:
        frappe.db.set_value("User", usr, "last_login", None, update_modified=False)
        frappe.local.response['http_status_code'] = 401
        frappe.local.response['message'] = "Invalid Login Credentials"
        return
    except Exception as e:
        frappe.log_error(title="SFA Login Exception", message=frappe.get_traceback())
        frappe.local.response['http_status_code'] = 500
        frappe.local.response['message'] = "Server error during login."
        return

    # === TEMPORARILY DISABLED ROLE CHECK FOR PRESENTATION ===
    # user_roles = frappe.get_roles(frappe.session.user)
    # if "SFA Mobile User" not in user_roles:
    #     login_manager.logout()
    #     frappe.local.response['http_status_code'] = 403
    #     frappe.local.response['message'] = "User missing 'SFA Mobile User' role."
    #     return
    # ========================================================

    frappe.local.response.message = {
        "message": "Logged In",
        "home_page": "/app",
        "full_name": frappe.session.user_full_name
    }

@frappe.whitelist(allow_guest=False)
def create_erp_document(payload):
    try:
        data = json.loads(payload)
        if not data.get("company"):
            company = frappe.db.get_value("Company", {}, "name")
            if not company:
                frappe.throw("No Company found in ERPNext database!")
            data["company"] = company
        
        doc = frappe.get_doc(data)
        doc.insert(ignore_permissions=True)
        if data.get("docstatus") == 1:
            doc.submit()
        return doc.name
    except Exception:
        frappe.log_error(frappe.get_traceback(), "SFA CRM Sync Error")
        raise

@frappe.whitelist()
def get_sfa_settings():
    try:
        settings = frappe.get_doc("SFA Settings")
        user = frappe.session.user
        user_roles = frappe.get_roles(user)
        
        disabled_features = set()

        for p in settings.permissions:
            if p.disabled:
                is_match = (p.apply_to == 'User' and p.user_or_role == user) or \
                           (p.apply_to == 'Role' and p.user_or_role in user_roles)
                if is_match:
                    disabled_features.add(p.feature.lower().replace(" ", "_"))
        
        return {
            "logo_url": settings.app_logo,
            "company_name": settings.company_name_override,
            "disabled_features": list(disabled_features)
        }
    except frappe.DoesNotExistError:
        return {
            "logo_url": None,
            "company_name": None,
            "disabled_features": []
        }

@frappe.whitelist()
def get_map_data():
    customers = frappe.get_all(
        "Customer",
        filters={
            "custom_latitude": ["is", "set"],
            "custom_longitude": ["is", "set"],
        },
        fields=["name", "customer_name", "custom_latitude", "custom_longitude", "territory"],
        limit=500
    )
    return customers

@frappe.whitelist()
def force_log_location(latitude, longitude, timestamp, activity):
    try:
        # Create doc ignoring permissions
        doc = frappe.get_doc({
            "doctype": "Salesperson Location Log",
            "sales_person": frappe.session.user, # Safely use email ID as identifier
            "latitude": latitude,
            "longitude": longitude,
            "timestamp": timestamp,
            "activity": activity
        })
        doc.insert(ignore_permissions=True)
        frappe.db.commit() # Force save immediately
        return {"status": "success", "name": doc.name}
    except Exception as e:
        frappe.log_error("Force Location Log Failed", str(e))
        return {"status": "error", "message": str(e)}

def run_full_setup():
    """
    Run this once to create all DocTypes, Roles, Reports, and Client Scripts.
    Execute with: bench --site SITENAME run-script apps/sfa_crm/setup.py
    """
    import os
    frappe.flags.in_import = True

    print("Step 1: Creating Role: SFA Mobile User...")
    if not frappe.db.exists("Role", "SFA Mobile User"):
        frappe.get_doc({
            "doctype": "Role",
            "role_name": "SFA Mobile User",
            "desk_access": 1
        }).insert(ignore_permissions=True)
        frappe.db.commit()
        print("  Role created.")
    else:
        print("  Role already exists.")

    print("Step 2: Creating SFA Feature Permission child DocType...")
    if not frappe.db.exists("DocType", "SFA Feature Permission"):
        frappe.get_doc({
            "doctype": "DocType",
            "name": "SFA Feature Permission",
            "module": "Sfa Crm",
            "custom": 1,
            "istable": 1,
            "fields": [
                {"fieldname": "apply_to", "label": "Apply To", "fieldtype": "Select", "options": "User\nRole", "in_list_view": 1},
                {"fieldname": "user_or_role", "label": "User or Role", "fieldtype": "Dynamic Link", "options": "apply_to", "in_list_view": 1},
                {"fieldname": "feature", "label": "Feature", "fieldtype": "Select", "options": "Expenses\nCustomers\nOrders\nPayments", "in_list_view": 1},
                {"fieldname": "disabled", "label": "Disabled", "fieldtype": "Check", "default": "1", "in_list_view": 1}
            ]
        }).insert(ignore_permissions=True)
        frappe.db.commit()
        print("  SFA Feature Permission created.")
    else:
        print("  SFA Feature Permission already exists.")

    print("Step 3: Creating SFA Settings singleton DocType...")
    if not frappe.db.exists("DocType", "SFA Settings"):
        frappe.get_doc({
            "doctype": "DocType",
            "name": "SFA Settings",
            "module": "Sfa Crm",
            "custom": 1,
            "issingle": 1,
            "fields": [
                {"fieldname": "app_logo", "label": "App Logo", "fieldtype": "Attach Image"},
                {"fieldname": "company_name_override", "label": "Company Name Override", "fieldtype": "Data"},
                {"fieldname": "sb_perms", "label": "App Permissions", "fieldtype": "Section Break"},
                {"fieldname": "permissions", "label": "Feature Permissions", "fieldtype": "Table", "options": "SFA Feature Permission"}
            ]
        }).insert(ignore_permissions=True)
        frappe.db.commit()
        print("  SFA Settings created.")
    else:
        print("  SFA Settings already exists.")

    print("Step 4: Creating Route Customer child DocType...")
    if not frappe.db.exists("DocType", "Route Customer"):
        frappe.get_doc({
            "doctype": "DocType",
            "name": "Route Customer",
            "module": "Sfa Crm",
            "custom": 1,
            "istable": 1,
            "fields": [
                {"fieldname": "customer", "label": "Customer", "fieldtype": "Link", "options": "Customer", "in_list_view": 1},
                {"fieldname": "customer_name", "label": "Customer Name", "fieldtype": "Data", "fetch_from": "customer.customer_name", "read_only": 1, "in_list_view": 1}
            ]
        }).insert(ignore_permissions=True)
        frappe.db.commit()
        print("  Route Customer created.")
    else:
        print("  Route Customer already exists.")

    print("Step 5: Creating Sales Route DocType...")
    if not frappe.db.exists("DocType", "Sales Route"):
        frappe.get_doc({
            "doctype": "DocType",
            "name": "Sales Route",
            "module": "Sfa Crm",
            "custom": 1,
            "fields": [
                {"fieldname": "route_name", "label": "Route Name", "fieldtype": "Data", "reqd": 1, "in_list_view": 1},
                {"fieldname": "sales_person_user", "label": "Assigned To (User)", "fieldtype": "Link", "options": "User", "reqd": 1, "in_list_view": 1},
                {"fieldname": "sb_customers", "label": "Customers in this Route", "fieldtype": "Section Break"},
                {"fieldname": "customers", "label": "Customers", "fieldtype": "Table", "options": "Route Customer"}
            ]
        }).insert(ignore_permissions=True)
        frappe.db.commit()
        print("  Sales Route created.")
    else:
        print("  Sales Route already exists.")

    print("Step 6: Creating Salesperson Tracking Map DocType...")
    if not frappe.db.exists("DocType", "Salesperson Tracking Map"):
        frappe.get_doc({
            "doctype": "DocType",
            "name": "Salesperson Tracking Map",
            "module": "Sfa Crm",
            "custom": 1,
            "issingle": 0,
            "fields": [
                {"fieldname": "sales_person", "label": "Salesperson Email", "fieldtype": "Data", "reqd": 1, "in_list_view": 1},
                {"fieldname": "date", "label": "Date", "fieldtype": "Date", "default": "Today", "reqd": 1, "in_list_view": 1},
                {"fieldname": "map_view", "label": "Map View", "fieldtype": "HTML"}
            ]
        }).insert(ignore_permissions=True)
        frappe.db.commit()
        print("  Salesperson Tracking Map created.")
    else:
        print("  Salesperson Tracking Map already exists.")

    print("Step 7: Creating SFA Leads Report...")
    if not frappe.db.exists("Report", "SFA Leads"):
        frappe.get_doc({
            "doctype": "Report",
            "report_name": "SFA Leads",
            "ref_doctype": "Customer",
            "report_type": "Query Report",
            "is_standard": "Yes",
            "module": "Sfa Crm",
            "query": """SELECT
    c.name as 'Customer:Link/Customer:200',
    c.customer_name as 'Customer Name:Data:250',
    c.territory as 'Territory:Link/Territory:150',
    c.creation as 'Created On:Datetime:150'
FROM `tabCustomer` c
LEFT JOIN `tabSales Order` so ON c.name = so.customer
WHERE c.disabled = 0
GROUP BY c.name
HAVING COUNT(so.name) = 0
ORDER BY c.creation DESC"""
        }).insert(ignore_permissions=True)
        frappe.db.commit()
        print("  SFA Leads Report created.")
    else:
        print("  SFA Leads Report already exists.")

    print("Step 8: Creating Daily Collections Report...")
    if not frappe.db.exists("Report", "SFA Daily Collections"):
        frappe.get_doc({
            "doctype": "Report",
            "report_name": "SFA Daily Collections",
            "ref_doctype": "Payment Entry",
            "report_type": "Query Report",
            "is_standard": "Yes",
            "module": "Sfa Crm",
            "query": """SELECT
    pe.posting_date as 'Date:Date:120',
    u.full_name as 'Collected By:Data:200',
    pe.party_name as 'Customer:Data:200',
    pe.mode_of_payment as 'Mode:Data:120',
    pe.paid_amount as 'Amount:Currency:150'
FROM `tabPayment Entry` pe
JOIN `tabUser` u ON pe.owner = u.email
WHERE pe.docstatus = 1 AND pe.payment_type = 'Receive'
ORDER BY pe.posting_date DESC"""
        }).insert(ignore_permissions=True)
        frappe.db.commit()
        print("  SFA Daily Collections Report created.")
    else:
        print("  SFA Daily Collections Report already exists.")

    print("Step 9: Creating Animated Tracker Map Client Script...")
    if not frappe.db.exists("Client Script", "SFA Animated Tracker Map"):
        tracker_script = """frappe.ui.form.on("Salesperson Tracking Map", {
    refresh(frm) {
        frm.add_custom_button(__('Load Map'), () => { frm.trigger('render_map'); });
        if (frm.doc.sales_person && frm.doc.date) {
            frm.trigger('render_map');
        }
    },
    sales_person(frm) { if (frm.doc.sales_person && frm.doc.date) frm.trigger('render_map'); },
    date(frm) { if (frm.doc.sales_person && frm.doc.date) frm.trigger('render_map'); },
    render_map(frm) {
        if (!frm.doc.sales_person || !frm.doc.date) {
            frappe.msgprint("Please enter a Salesperson Email and Date first.");
            return;
        }
        frm.get_field("map_view").$wrapper.html(`
            <div style="padding: 10px; border: 1px solid #d1d8dd; border-radius: 6px; margin-top: 10px;">
                <div style="margin-bottom: 10px; display: flex; align-items: center; gap: 10px;">
                    <button id="sfa-btn-play" class="btn btn-primary btn-sm">▶ Play Route</button>
                    <button id="sfa-btn-pause" class="btn btn-default btn-sm">⏸ Pause</button>
                    <button id="sfa-btn-reset" class="btn btn-default btn-sm">⏮ Reset</button>
                    <span id="sfa-tracker-info" style="font-weight: bold; color: #555; font-size: 12px;"></span>
                </div>
                <div id="sfa_tracker_map" style="height: 550px; width: 100%; z-index: 1; border-radius: 4px;"></div>
            </div>
        `);
        let map_div = frm.get_field("map_view").$wrapper.find('#sfa_tracker_map')[0];
        frappe.call({
            method: "frappe.client.get_list",
            args: {
                doctype: "Salesperson Location Log",
                filters: { "sales_person": frm.doc.sales_person, "timestamp": ["between", [frm.doc.date + " 00:00:00", frm.doc.date + " 23:59:59"]] },
                fields: ["latitude", "longitude", "timestamp", "activity"],
                limit: 2000,
                order_by: "timestamp asc"
            },
            callback: function(r) {
                let logs = (r.message || []).filter(l => l.latitude && l.longitude);
                if (logs.length === 0) {
                    frm.get_field("map_view").$wrapper.find('#sfa-tracker-info').text("No location logs found for this date and user.");
                    frm.get_field("map_view").$wrapper.find('#sfa_tracker_map').html('<div style="display:flex;align-items:center;justify-content:center;height:100%;color:gray;font-size:16px;">No data to display</div>');
                    return;
                }
                frm.get_field("map_view").$wrapper.find('#sfa-tracker-info').text(`Found ${logs.length} location points`);
                if (frm.sfa_map_instance) frm.sfa_map_instance.remove();
                frm.sfa_map_instance = L.map(map_div).setView([parseFloat(logs[0].latitude), parseFloat(logs[0].longitude)], 14);
                L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { attribution: '© OpenStreetMap' }).addTo(frm.sfa_map_instance);
                let latlngs = logs.map(l => [parseFloat(l.latitude), parseFloat(l.longitude)]);
                L.polyline(latlngs, { color: '#1976D2', weight: 3, opacity: 0.7 }).addTo(frm.sfa_map_instance);
                let startIcon = L.divIcon({ html: '<div style="background:#4CAF50;width:14px;height:14px;border-radius:50%;border:2px solid white;"></div>', iconSize: [14, 14] });
                let endIcon = L.divIcon({ html: '<div style="background:#D32F2F;width:14px;height:14px;border-radius:50%;border:2px solid white;"></div>', iconSize: [14, 14] });
                L.marker(latlngs[0], { icon: startIcon }).addTo(frm.sfa_map_instance).bindPopup("Start: " + logs[0].timestamp);
                L.marker(latlngs[latlngs.length - 1], { icon: endIcon }).addTo(frm.sfa_map_instance).bindPopup("End: " + logs[logs.length - 1].timestamp);
                let movingMarker = L.circleMarker(latlngs[0], { radius: 9, fillColor: "#FF9800", color: "#fff", weight: 2, fillOpacity: 1 }).addTo(frm.sfa_map_instance);
                let currentIndex = 0;
                let timer = null;
                const updateStatus = (i) => {
                    frm.get_field("map_view").$wrapper.find('#sfa-tracker-info').text(`Point ${i + 1}/${logs.length} | Time: ${logs[i].timestamp} | ${logs[i].activity}`);
                };
                const playRoute = () => {
                    clearInterval(timer);
                    timer = setInterval(() => {
                        if (currentIndex >= latlngs.length) {
                            clearInterval(timer);
                            frm.get_field("map_view").$wrapper.find('#sfa-tracker-info').text("Route finished.");
                            return;
                        }
                        movingMarker.setLatLng(latlngs[currentIndex]);
                        frm.sfa_map_instance.panTo(latlngs[currentIndex], { animate: true });
                        updateStatus(currentIndex);
                        currentIndex++;
                    }, 800);
                };
                frm.get_field("map_view").$wrapper.find('#sfa-btn-play').on('click', playRoute);
                frm.get_field("map_view").$wrapper.find('#sfa-btn-pause').on('click', () => clearInterval(timer));
                frm.get_field("map_view").$wrapper.find('#sfa-btn-reset').on('click', () => { clearInterval(timer); currentIndex = 0; movingMarker.setLatLng(latlngs[0]); frm.sfa_map_instance.setView(latlngs[0], 14); updateStatus(0); });
                updateStatus(0);
            }
        });
    }
});"""
        frappe.get_doc({
            "doctype": "Client Script",
            "name": "SFA Animated Tracker Map",
            "dt": "Salesperson Tracking Map",
            "script": tracker_script,
            "enabled": 1
        }).insert(ignore_permissions=True)
        frappe.db.commit()
        print("  Animated Tracker Map Client Script created.")
    else:
        print("  Animated Tracker Map Client Script already exists.")

    print("Step 10: Creating Customer Territory Map Client Script...")
    if not frappe.db.exists("Client Script", "SFA Customer Territory Map"):
        territory_script = """frappe.ui.form.on("Customer Territory Map", {
    refresh(frm) {
        frm.add_custom_button(__('Load Customer Map'), () => { frm.trigger('render_map'); });
    },
    render_map(frm) {
        frm.get_field("map_view").$wrapper.html(`
            <div style="padding: 10px; border: 1px solid #d1d8dd; border-radius: 6px; margin-top: 10px;">
                <h4 style="margin-top:0;">Customer Territory Map</h4>
                <div id="sfa_territory_map" style="height: 550px; width: 100%;"></div>
            </div>
        `);
        let map_div = frm.get_field("map_view").$wrapper.find('#sfa_territory_map')[0];
        frappe.call({
            method: "sfa_crm.api.get_map_data",
            callback: function(r) {
                let customers = r.message || [];
                if (frm.territory_map) frm.territory_map.remove();
                let centerLat = -6.3690, centerLng = 34.8888;
                if (customers.length > 0) { centerLat = parseFloat(customers[0].custom_latitude); centerLng = parseFloat(customers[0].custom_longitude); }
                frm.territory_map = L.map(map_div).setView([centerLat, centerLng], 8);
                L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { attribution: '© OpenStreetMap' }).addTo(frm.territory_map);
                customers.forEach(c => {
                    let lat = parseFloat(c.custom_latitude), lng = parseFloat(c.custom_longitude);
                    if (lat && lng) L.marker([lat, lng]).addTo(frm.territory_map).bindPopup(`<b>${c.customer_name}</b><br>Territory: ${c.territory || 'N/A'}`);
                });
                if (customers.length === 0) frappe.msgprint("No customers with GPS coordinates found.");
            }
        });
    }
});"""
        frappe.get_doc({
            "doctype": "Client Script",
            "name": "SFA Customer Territory Map",
            "dt": "Customer Territory Map",
            "script": territory_script,
            "enabled": 1
        }).insert(ignore_permissions=True)
        frappe.db.commit()
        print("  Customer Territory Map Client Script created.")
    else:
        print("  Customer Territory Map Client Script already exists.")

    print("Step 11: Updating hooks.py for Git fixtures export...")
    hooks_path = frappe.get_app_path('sfa_crm', 'hooks.py')
    with open(hooks_path, 'r') as f:
        hooks_content = f.read()
    if 'fixtures' not in hooks_content:
        with open(hooks_path, 'a') as f:
            f.write('\n# Export these to Git via bench export-fixtures\n')
            f.write('fixtures = [\n')
            f.write('    "Role",\n')
            f.write('    "Client Script",\n')
            f.write('    "Report",\n')
            f.write('    "Custom Field",\n')
            f.write('    "Property Setter",\n')
            f.write('    {"dt": "DocType", "filters": [["custom", "=", 1], ["module", "=", "Sfa Crm"]]}\n')
            f.write(']\n')
        print("  hooks.py updated with fixtures.")
    else:
        print("  hooks.py already has fixtures defined.")

    print("Step 12: Exporting fixtures to Git folder...")
    import subprocess
    result = subprocess.run(['bench', 'export-fixtures'], capture_output=True, text=True, cwd='/home/frappe/frappe-bench')
    print(result.stdout)
    if result.returncode != 0:
        print("Export error:", result.stderr)
    else:
        print("All fixtures exported to apps/sfa_crm/sfa_crm/fixtures/")

    print("")
    print("=" * 60)
    print("SFA CRM SETUP COMPLETE!")
    print("=" * 60)
    print("Created:")
    print("  Role: SFA Mobile User")
    print("  DocType: SFA Settings")
    print("  DocType: SFA Feature Permission")
    print("  DocType: Sales Route")
    print("  DocType: Route Customer")
    print("  DocType: Salesperson Tracking Map")
    print("  Report: SFA Leads")
    print("  Report: SFA Daily Collections")
    print("  Client Script: SFA Animated Tracker Map")
    print("  Client Script: SFA Customer Territory Map")
    print("  Git Export: Complete (bench migrate on new server to install)")
    print("=" * 60)
