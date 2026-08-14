import frappe
import json
import traceback
import time
from frappe.utils.password import get_decrypted_password

def get_single_val(doctype, fieldname):
    res = frappe.db.sql("SELECT value FROM tabSingles WHERE doctype=%s AND field=%s", (doctype, fieldname))
    return res[0][0] if res else None

def set_default_company(doc, method=None):
    if not doc.company:
        company = frappe.defaults.get_user_default("Company")
        if not company:
            comp_list = frappe.db.get_all("Company", limit=1)
            company = comp_list[0].name if comp_list else None
        doc.company = company

def get_valid_link_value(doctype, fieldname="sales_person"):
    user_email = frappe.session.user
    try:
        meta = frappe.get_meta(doctype)
        field = meta.get_field(fieldname)
        if not field or field.fieldtype != "Link":
            return user_email
            
        options = field.options
        if options == "User":
            return user_email
            
        if options == "Employee":
            emp = frappe.db.get_value("Employee", {"user_id": user_email}, "name")
            return emp or user_email
            
        if options == "Sales Person":
            emp = frappe.db.get_value("Employee", {"user_id": user_email}, "name")
            if emp:
                sp = frappe.db.get_value("Sales Person", {"employee": emp}, "name")
                if sp: return sp
                
            if frappe.db.exists("Sales Person", user_email):
                return user_email
                
            full_name = frappe.db.get_value("User", user_email, "full_name") or user_email
            if frappe.db.exists("Sales Person", full_name):
                return full_name
                
            sp_doc = frappe.new_doc("Sales Person")
            sp_doc.sales_person_name = full_name
            if emp: sp_doc.employee = emp
            sp_doc.insert(ignore_permissions=True)
            frappe.db.commit()
            return sp_doc.name
            
        return user_email
    except Exception:
        return user_email

def resolve_customer_or_lead(input_name):
    if frappe.db.exists("Customer", input_name):
        return "Customer", input_name
    cust = frappe.db.get_value("Customer", {"customer_name": input_name}, "name")
    if cust: return "Customer", cust
    if frappe.db.exists("Lead", input_name):
        return "Lead", input_name
    lead = frappe.db.get_value("Lead", {"lead_name": input_name}, "name")
    if lead: return "Lead", lead
    return None, None

def process_base64_image(base64_data, doctype, docname, fieldname=None):
    if "," in base64_data:
        base64_data = base64_data.split(",")[1]
    file_doc = frappe.get_doc({
        "doctype": "File",
        "file_name": f"img_{int(time.time())}_{frappe.generate_hash(length=4)}.jpg",
        "attached_to_doctype": doctype,
        "attached_to_name": docname,
        "content": base64_data,
        "decode": True,
        "is_private": 0
    })
    file_doc.insert(ignore_permissions=True)
    if fieldname:
        frappe.db.sql(f"UPDATE `tab{doctype}` SET `{fieldname}`=%s WHERE name=%s", (file_doc.file_url, docname))

def convert_lead_to_customer(lead_id, company):
    existing_cust = frappe.db.get_value("Customer", {"lead_name": lead_id}, "name")
    if existing_cust: return existing_cust

    lead = frappe.get_doc("Lead", lead_id)
    cust = frappe.new_doc("Customer")
    cust.customer_name = lead.lead_name or lead.company_name or lead.first_name
    cust.lead_name = lead.name
    cust.company = company
    
    cg = get_single_val("Selling Settings", "customer_group")
    if not cg:
        cg_list = frappe.db.get_all("Customer Group", limit=1)
        cg = cg_list[0].name if cg_list else "Commercial"
    cust.customer_group = cg
    
    cust.territory = lead.territory or "All Territories"
    cust.custom_latitude = lead.custom_latitude
    cust.custom_longitude = lead.custom_longitude
    cust.mobile_no = lead.mobile_no
    cust.image = lead.image
    cust.custom_storefront = lead.image 
    cust.custom_business_type = getattr(lead, 'custom_business_type', None)
    
    cust.flags.ignore_mandatory = True
    cust.insert(ignore_permissions=True)
    lead.db_set("status", "Converted")
    return cust.name

@frappe.whitelist(allow_guest=True)
def get_site_logo():
    logo = get_single_val("Website Settings", "app_logo") or get_single_val("Website Settings", "banner_image")
    if logo: return {"logo_url": frappe.utils.get_url(logo)}
    return {"logo_url": None}

@frappe.whitelist(allow_guest=True)
def sfa_login(usr, pwd):
    try:
        login_manager = frappe.auth.LoginManager()
        login_manager.authenticate(user=usr, pwd=pwd)
        login_manager.post_login()
        frappe.local.response.message = {
            "message": "Logged In",
            "home_page": "/app",
            "full_name": frappe.session.user_full_name
        }
    except Exception:
        frappe.local.response['http_status_code'] = 401
        frappe.local.response['message'] = "Invalid Credentials"

@frappe.whitelist()
def get_api_token():
    """Return (creating if necessary) the logged-in user's permanent API token.

    Called by the CherryCRM mobile app immediately after login, while the
    fresh sid session is still valid. The returned "key:secret" pair is then
    used as `Authorization: token key:secret` on every subsequent request,
    so the mobile session never expires (until the user logs out or the
    token is regenerated/revoked in ERPNext).
    """
    user = frappe.session.user
    if not user or user == "Guest":
        frappe.throw("Not permitted", frappe.AuthenticationError)

    user_doc = frappe.get_doc("User", user)

    # Ensure an api_key exists
    api_key = user_doc.api_key
    if not api_key:
        api_key = frappe.generate_hash(length=15)
        user_doc.api_key = api_key

    # Reuse the existing api_secret if present, otherwise generate one.
    api_secret = None
    if user_doc.get("api_secret"):
        api_secret = get_decrypted_password(
            "User", user, "api_secret", raise_exception=False
        )
    if not api_secret:
        api_secret = frappe.generate_hash(length=15)
        user_doc.api_secret = api_secret

    user_doc.flags.ignore_permissions = True
    user_doc.save(ignore_permissions=True)
    frappe.db.commit()

    return {"token": f"{api_key}:{api_secret}"}

@frappe.whitelist()
def get_sfa_settings():
    try:
        logo = get_single_val("Website Settings", "app_logo") or get_single_val("Website Settings", "banner_image")
        company_name = get_single_val("SFA Settings", "company_name_override")
        if not company_name:
            company_name = frappe.defaults.get_user_default("Company")
            if not company_name:
                c_list = frappe.db.get_all("Company", limit=1)
                company_name = c_list[0].name if c_list else "Koda Technologies"
        
        return {
            "logo_url": frappe.utils.get_url(logo) if logo else None,
            "company_name": company_name,
            "enable_delivery_module": int(get_single_val("SFA Settings", "enable_delivery_module") or 0),
            "enable_expense_module": int(get_single_val("SFA Settings", "enable_expense_module") or 0)
        }
    except Exception:
        return {"logo_url": None, "company_name": "Koda Technologies", "enable_delivery_module": 0, "enable_expense_module": 0}

@frappe.whitelist()
def sync_client(payload):
    data = json.loads(payload)
    try:
        phone = data.get("phone")
        if phone:
            existing_lead = frappe.db.get_value("Lead", {"mobile_no": phone}, "name")
            if existing_lead:
                return {"success": True, "name": existing_lead, "message": "Lead already exists"}
                
        doc = frappe.new_doc("Lead")
        doc.first_name = data.get("name", "Unknown")
        doc.lead_name = data.get("name", "Unknown")
        comp_list = frappe.db.get_all("Company", limit=1)
        doc.company = frappe.defaults.get_user_default("Company") or (comp_list[0].name if comp_list else None)
        t_list = frappe.db.get_all("Territory", limit=1)
        doc.territory = t_list[0].name if t_list else "All Territories"
        doc.mobile_no = phone
        doc.phone = phone
        doc.custom_business_type = data.get("businessType")
        doc.custom_latitude = data.get("lat")
        doc.custom_longitude = data.get("lng")
        doc.flags.ignore_mandatory = True
        doc.insert(ignore_permissions=True)
        
        notes = data.get("notes", "")
        role = data.get("contactRole", "")
        owner_phone = data.get("ownerPhone", "")
        doc.add_comment("Comment", text=f"**KYC Details**\nRole: {role}\nOwner Phone: {owner_phone}\n\n**Observations:**\n{notes}")
        
        for i, photo_b64 in enumerate(data.get("photosBase64", [])):
            process_base64_image(photo_b64, "Lead", doc.name, "image" if i == 0 else None)
            
        frappe.db.commit()
        return {"success": True, "name": doc.name}
    except Exception as e:
        return {"success": False, "error": str(e), "trace": traceback.format_exc()}

@frappe.whitelist()
def sync_visit(payload):
    data = json.loads(payload)
    try:
        doctype_found, docname_found = resolve_customer_or_lead(data.get("customer"))
        if not doctype_found:
            return {"success": False, "error": f"Client '{data.get('customer')}' not found."}
            
        comp_list = frappe.db.get_all("Company", limit=1)
        company = frappe.defaults.get_user_default("Company") or (comp_list[0].name if comp_list else None)
        
        if doctype_found == "Lead":
            docname_found = convert_lead_to_customer(docname_found, company)
            
        sales_person = get_valid_link_value("Visit Log", "sales_person")
        
        doc = frappe.get_doc({
            "doctype": "Visit Log",
            "sales_person": sales_person,
            "customer": docname_found,
            "start_time": data.get("start_time", "").replace("T", " ")[:19],
            "end_time": data.get("end_time", "").replace("T", " ")[:19],
            "outcome": data.get("outcome"),
            "no_order_reason": data.get("no_order_reason"),
            "custom_latitude": data.get("lat"),
            "custom_longitude": data.get("lng")
        })
        doc.flags.ignore_mandatory = True
        doc.insert(ignore_permissions=True)
        doc.submit()
        
        if data.get("photoBase64"):
            process_base64_image(data.get("photoBase64"), "Visit Log", doc.name, "evidence_photo")
            
        frappe.db.commit()
        return {"success": True, "name": doc.name}
    except Exception as e:
        frappe.log_error(title="SFA Sync Visit Failed", message=traceback.format_exc())
        return {"success": False, "error": str(e), "trace": traceback.format_exc()}

@frappe.whitelist()
def sync_order(doc_type, payload):
    data = json.loads(payload)
    try:
        doctype_found, docname_found = resolve_customer_or_lead(data.get("customer"))
        if not doctype_found: return {"success": False, "error": f"Customer/Lead '{data.get('customer')}' not found."}
            
        comp_list = frappe.db.get_all("Company", limit=1)
        company = frappe.defaults.get_user_default("Company") or (comp_list[0].name if comp_list else None)
        if doctype_found == "Lead": docname_found = convert_lead_to_customer(docname_found, company)
            
        data["customer"] = docname_found
        data["company"] = company
        data["doctype"] = doc_type
        data["docstatus"] = 1
        
        doc = frappe.get_doc(data)
        doc.flags.ignore_mandatory = True
        doc.insert(ignore_permissions=True)
        doc.submit()
        return {"success": True, "name": doc.name}
    except Exception as e:
        frappe.log_error(title="SFA Sync Order Failed", message=traceback.format_exc())
        return {"success": False, "error": str(e), "trace": traceback.format_exc()}

@frappe.whitelist()
def force_log_location(latitude, longitude, timestamp, activity):
    try:
        sales_person = get_valid_link_value("Salesperson Location Log", "sales_person")
            
        doc = frappe.new_doc("Salesperson Location Log")
        doc.sales_person = sales_person
        doc.latitude = str(latitude)
        doc.longitude = str(longitude)
        doc.timestamp = timestamp
        doc.activity = activity
        
        if doc.meta.has_field("custom_salesperson_name"):
            doc.custom_salesperson_name = frappe.session.user_full_name
            
        doc.flags.ignore_mandatory = True
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        return {"status": "success", "name": doc.name}
    except Exception as e:
        frappe.log_error(title="SFA Location Log Failed", message=traceback.format_exc())
        return {"status": "error", "message": str(e), "trace": traceback.format_exc()}

@frappe.whitelist()
def get_map_data():
    return frappe.db.get_all("Customer", fields=["name", "customer_name", "custom_latitude", "custom_longitude", "territory"])
