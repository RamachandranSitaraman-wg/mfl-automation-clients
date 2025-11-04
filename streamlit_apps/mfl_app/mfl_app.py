# import streamlit as st
# import importlib
# import time
# from typing import Dict, Any
#
#
# import requests
import re

package_name = "realvalidation"
normalized = re.sub(r"[-_.]+", "_", package_name).upper()
print(f"!!SETUPTOOLS_SCM_PRETEND_VERSION_FOR_{normalized}")
import os

os.environ["SETUPTOOLS_SCM_PRETEND_VERSION_FOR_REALVALIDATION"] = "2.0.0"

# Then rest of your imports...
import streamlit as st
import requests
import json
import os
from typing import Dict, Any
from pathlib import Path
import time
from datetime import datetime

# Import the phone provider lookup function
try:
    from realvalidation import get_phone_provider

    PHONE_PROVIDER_AVAILABLE = True
except ImportError:
    PHONE_PROVIDER_AVAILABLE = False
    st.warning("Phone provider validation module not found. Phone provider lookup will be skipped.")
import importlib
# =====================================================
# CONFIGURATION
# =====================================================
from realvalidation import get_phone_provider

MIDDLEWARE_URL = "http://localhost:8000"  # Adjust for your setup
STATUS_POLLING_INTERVAL = 30
import os

# Prevent setuptools-scm from throwing version lookup errors
os.environ["SETUPTOOLS_SCM_PRETEND_VERSION_FOR_REALVALIDATION"] = "1.0.0"

MACRO_CONFIG = {
    "new": {
        "id": 22998852760215,
        "name": "MFL::Client Communication:: Thank you for Submitting",
        "trigger_status": "new",
    },
    "open": {
        "id": 22998852854167,
        "name": "MFL::Client Communication::Tier 1 Carrier",
        "trigger_status": "open",
    },
    "solved": {
        "id": 22998828412695,
        "name": "MFL::Client Communication:: Successful Phone Number Takedown",
        "trigger_status": "solved",
    },
}


def check_phone_duplicate_via_middleware(phone_number: str):
    """Check if phone number exists via middleware."""
    try:
        resp = requests.post(
            f"{MIDDLEWARE_URL}/mfl/check_phone_duplicate",
            json={"phone_number": phone_number},
            timeout=30
        )

        st.info(f"🔍 Duplicate check response status: {resp.status_code}")

        if resp.status_code == 200:
            result = resp.json()
            st.info(f"📊 Duplicate check result: {result}")
            return result
        else:
            error_msg = f"Status {resp.status_code}: {resp.text[:200]}"
            st.warning(f"⚠️ Could not check for duplicates: {error_msg}")
            return {"exists": False, "error": error_msg}
    except requests.exceptions.Timeout:
        st.error("⏱️ Timeout while checking for duplicates (>30s)")
        return {"exists": False, "error": "Timeout"}
    except Exception as e:
        st.error(f"❌ Error checking duplicates: {e}")
        return {"exists": False, "error": str(e)}


# =====================================================
# LAZY LOAD REALVALIDATION (prevents setuptools-scm issue)
# =====================================================

def lazy_get_phone_provider(phone_number: str) -> str | None:
    """Safely import and call realvalidation.get_phone_provider at runtime."""
    try:
        os.environ.setdefault("SETUPTOOLS_SCM_PRETEND_VERSION_FOR_REALVALIDATION", "1.0.0")
        # realvalidation = importlib.import_module("realvalidation")
        # func = getattr(realvalidation, "get_phone_provider", None)
        from realvalidation import get_phone_provider

        func = get_phone_provider
        if func:
            return func(phone_number)
    except Exception as e:
        print(f"[WARN1] Lazy load of realvalidation failed: {e}")
    return None


PHONE_PROVIDER_AVAILABLE = True


# =====================================================
# ZENDESK HELPERS (for macros & polling)
# =====================================================

def load_zendesk_config() -> Dict[str, Any] | None:
    """Load Zendesk config from .streamlit/secrets.toml"""
    try:
        z = st.secrets["zendesk"]
        cfg = {
            "subdomain": z["subdomain"],
            "email": z["email"],
            "api_token": z["api_token"],
            "form_id": z["form_id"],
            "custom_fields": z.get("custom_fields", {}),
            "phone_provider_mapping": z.get("phone_provider_mapping", {}),
        }
        # Keep only set custom fields
        cfg["custom_fields"] = {k: v for k, v in cfg["custom_fields"].items() if v}
        return cfg
    except Exception as e:
        st.error(f"❌ Failed to load Zendesk secrets: {e}")
        return None


def zendesk_auth(config: Dict[str, str]):
    return (f"{config['email']}/token", config["api_token"])


def get_ticket_status(ticket_id: str, config: Dict[str, str]):
    """Fetch Zendesk ticket status with error handling."""
    try:
        url = f"https://{config['subdomain']}.zendesk.com/api/v2/tickets/{ticket_id}.json"
        resp = requests.get(url, auth=zendesk_auth(config))
        if resp.status_code == 200:
            return resp.json()
        else:
            print(f"[WARN] Status fetch failed {resp.status_code}: {resp.text}")
            return {"error": resp.text}
    except Exception as e:
        print(f"[ERROR] get_ticket_status: {e}")
        return {"error": str(e)}


def get_ticket_comments(ticket_id: str, config: Dict[str, str]):
    try:
        url = f"https://{config['subdomain']}.zendesk.com/api/v2/tickets/{ticket_id}/comments.json"
        resp = requests.get(url, auth=zendesk_auth(config))
        if resp.status_code == 200:
            return resp.json().get("comments", [])
        return []
    except Exception as e:
        print(f"[ERROR] get_ticket_comments: {e}")
        return []


def update_ticket_with_macro(ticket_id: str, macro_id: int, config: Dict[str, str]):
    """Apply a macro to a ticket by updating it."""
    try:
        preview_url = f"https://{config['subdomain']}.zendesk.com/api/v2/tickets/{ticket_id}/macros/{macro_id}/apply.json"
        update_url = f"https://{config['subdomain']}.zendesk.com/api/v2/tickets/{ticket_id}.json"
        auth = zendesk_auth(config)
        headers = {"Content-Type": "application/json"}

        preview = requests.get(preview_url, auth=auth, headers=headers)
        if preview.status_code != 200:
            return {"success": False, "error": f"Macro preview failed: {preview.status_code}"}

        macro_result = preview.json()["result"]
        payload = {"ticket": {}}

        if macro_result.get("comment"):
            payload["ticket"]["comment"] = macro_result["comment"]

        if "ticket" in macro_result:
            for k, v in macro_result["ticket"].items():
                if k != "id":
                    payload["ticket"][k] = v

        update = requests.put(update_url, json=payload, auth=auth, headers=headers)
        if update.status_code == 200:
            return {"success": True, "new_status": payload["ticket"].get("status")}
        return {"success": False, "error": f"Update failed {update.status_code}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# =====================================================
# MIDDLEWARE CALLS
# =====================================================

@st.cache_data(ttl=300)
def fetch_form_fields():
    """Get filtered form fields (only configured custom fields) from middleware"""
    resp = requests.get(f"{MIDDLEWARE_URL}/mfl/form_fields")
    if resp.status_code == 200:
        return resp.json()
    else:
        st.error(f"Failed to fetch form fields: {resp.text}")
        return {"success": False}


def create_ticket_via_middleware(payload: Dict[str, Any]):
    """Create ticket via middleware (which maps display → internal values)"""
    try:
        resp = requests.post(f"{MIDDLEWARE_URL}/mfl/create_ticket", json=payload)
        st.error(f"response is {resp.json()}")
        if resp.status_code == 200:
            return resp.json()
        else:
            st.error(f"Middleware error {resp.status_code}: {resp.text}")
            return {"success": False}
    except Exception as e:
        st.error(f"Error contacting middleware: {e}")
        return {"success": False}


def create_ticket_flow(ticket_payload: Dict[str, Any], zendesk_config: Dict[str, Any]):
    """Execute the actual ticket creation with provider lookup and macro application."""
    # Auto populate phone provider (hidden field)
    if PHONE_PROVIDER_AVAILABLE and ticket_payload.get("phone_number"):
        provider_name = lazy_get_phone_provider(ticket_payload["phone_number"])
        if provider_name:
            ticket_payload["phone_number_provider"] = provider_name

    st.info("Submitting ticket to middleware...")
    result = create_ticket_via_middleware(ticket_payload)
    st.error(f"Ticket created with result: {result}")

    if result.get("success"):
        ticket_id = result["ticket_id"]
        ticket_url = f"https://{zendesk_config['subdomain']}.zendesk.com/agent/tickets/{ticket_id}"

        st.session_state["ticket_id"] = ticket_id
        st.session_state["ticket_url"] = ticket_url
        st.session_state["last_status"] = "new"

        # Clear duplicate confirmation state
        st.session_state["duplicate_confirmed"] = False
        st.session_state["pending_ticket_data"] = None
        st.session_state["last_phone_number"] = None
        st.session_state["show_duplicate_warning"] = False

        # Apply initial macro (NEW)
        with st.spinner("Applying initial macro..."):
            macro_result = update_ticket_with_macro(ticket_id, MACRO_CONFIG["new"]["id"], zendesk_config)
            if macro_result.get("success"):
                st.success(f"Applied macro: {MACRO_CONFIG['new']['name']}")
            else:
                st.warning(f"Failed to apply macro: {macro_result.get('error')}")

        st.rerun()
    else:
        st.error(f"❌ Ticket creation failed: {result.get('error')}")


# =====================================================
# STREAMLIT UI
# =====================================================

st.set_page_config(page_title="🎫 MFL Ticket Creator", layout="wide")
st.title("📱 Mobile Feedback Loop Ticket Creator")

# Initialize session state for duplicate confirmation
if "duplicate_confirmed" not in st.session_state:
    st.session_state["duplicate_confirmed"] = False
if "pending_ticket_data" not in st.session_state:
    st.session_state["pending_ticket_data"] = None
if "last_phone_number" not in st.session_state:
    st.session_state["last_phone_number"] = None
if "show_duplicate_warning" not in st.session_state:
    st.session_state["show_duplicate_warning"] = False
if "duplicate_check_result" not in st.session_state:
    st.session_state["duplicate_check_result"] = None

# Persistent ticket link (survives reruns)
if "ticket_id" in st.session_state and "ticket_url" in st.session_state:
    st.success(f"✅ Ticket created successfully! [View in Zendesk]({st.session_state['ticket_url']})")

zendesk_config = load_zendesk_config()
if not zendesk_config:
    st.stop()

field_data = fetch_form_fields()
if not field_data.get("success"):
    st.stop()

st.success("✅ Zendesk form fields loaded via middleware.")

# Shortcuts to field metadata from middleware
dropdown_options: Dict[str, list] = field_data.get("dropdown_options", {})
field_mapping: Dict[str, Dict[str, Any]] = field_data.get("field_mapping", {})
# NOTE: middleware already filtered to only configured fields

# Map each configured logical field to its Zendesk field id
cf = zendesk_config["custom_fields"]
client_fid = str(cf.get("client_field_id", ""))
phone_fid = str(cf.get("phone_number_field_id", ""))
attack_fid = str(cf.get("attack_vector_field_id", ""))
cta_fid = str(cf.get("call_to_action_field_id", ""))
sources_fid = str(cf.get("sources_field_id", ""))
resolution_fid = str(cf.get("resolution_field_id", ""))
escalate_fid = str(cf.get("escalate_to_field_id", ""))
provider_fid = str(cf.get("phone_number_provider_field_id", ""))  # hidden in UI


def label_for(fid: str, fallback: str) -> str:
    return field_mapping.get(fid, {}).get("title", fallback)


def options_for(fid: str) -> list:
    return dropdown_options.get(fid, [])


# -----------------------------------------------------
# Handle "Create Anyway" button click (outside form)
# -----------------------------------------------------
if st.session_state.get("show_duplicate_warning"):
    duplicate_check = st.session_state.get("duplicate_check_result", {})
    pending_data = st.session_state.get("pending_ticket_data")

    if duplicate_check.get("error"):
        st.warning(f"⚠️ Duplicate check encountered an issue: {duplicate_check['error']}")

        col1, col2 = st.columns([3, 1])
        with col1:
            st.error("**Continue without duplicate check?**")
        with col2:
            if st.button("⚠️ Continue Anyway", type="primary", use_container_width=True, key="continue_without_check"):
                # Create ticket immediately
                create_ticket_flow(pending_data, zendesk_config)
                st.stop()

    elif duplicate_check.get("exists"):
        ticket_count = duplicate_check.get("count", 0)
        existing_tickets = duplicate_check.get("tickets", [])

        st.warning(
            f"⚠️ Found {ticket_count} existing ticket(s) with phone number: **{pending_data.get('phone_number')}**")

        # Display existing tickets
        st.markdown("### Existing Tickets:")

        status_emojis = {
            'new': '🆕',
            'open': '📂',
            'pending': '⏳',
            'solved': '✅',
            'closed': '🔒'
        }

        for ticket in existing_tickets:
            ticket_url = f"https://{zendesk_config['subdomain']}.zendesk.com/agent/tickets/{ticket['id']}"
            ticket_status = ticket.get('status', '')
            status_emoji = status_emojis.get(ticket_status, '❓')

            st.markdown(f"""
            - **Ticket #{ticket['id']}** {status_emoji} `{ticket_status.upper()}`
              - Subject: {ticket.get('subject', 'N/A')}
              - Created: {ticket.get('created_at', 'N/A')}
              - [View in Zendesk]({ticket_url})
            """)

        st.markdown("---")

        col1, col2, col3 = st.columns([2, 1, 1])
        with col1:
            st.error("**Do you still want to create a new ticket with this phone number?**")
        with col2:
            if st.button("⚠️ Create Anyway", type="primary", use_container_width=True, key="create_anyway_btn"):
                # Create ticket immediately
                create_ticket_flow(pending_data, zendesk_config)
                st.stop()
        with col3:
            if st.button("❌ Cancel", use_container_width=True, key="cancel_btn"):
                # Clear state and go back to form
                st.session_state["show_duplicate_warning"] = False
                st.session_state["duplicate_check_result"] = None
                st.session_state["pending_ticket_data"] = None
                st.rerun()

    # Show debug info
    with st.expander("🔧 Debug Info"):
        st.json(duplicate_check)

    st.stop()  # Don't show the form when warning is displayed

# -----------------------------------------------------
# Ticket Creation Form with dynamic dropdowns
# -----------------------------------------------------
with st.form("create_ticket_form"):
    st.subheader("Ticket Information")

    subject = st.text_input("Subject *")
    description = st.text_area("Description *")
    tags = st.text_input("Tags (comma separated)")

    col1, col2 = st.columns(2)

    with col1:
        # Client — dropdown
        client_opts = [""] + options_for(client_fid) if client_fid else [""]
        client = st.selectbox(label_for(client_fid, "Client *"), client_opts) if client_fid else st.text_input(
            "Client *")

        # Phone number — plain text
        phone_number = st.text_input("Phone Number")

        # Sources — dropdown or text based on field type/options
        sources_opts = [""] + options_for(sources_fid) if sources_fid else [""]
        sources = st.selectbox(label_for(sources_fid, "Sources"), sources_opts) if sources_fid and len(
            sources_opts) > 1 else st.text_input("Sources")

    with col2:
        # Attack Vector — dropdown
        attack_opts = [""] + options_for(attack_fid) if attack_fid else [""]
        attack_vector = st.selectbox(label_for(attack_fid, "Attack Vector"),
                                     attack_opts) if attack_fid else st.text_input("Attack Vector")

        # Call to Action — dropdown/text
        cta_opts = [""] + options_for(cta_fid) if cta_fid else [""]
        call_to_action = st.selectbox(label_for(cta_fid, "Call To Action"), cta_opts) if cta_fid and len(
            cta_opts) > 1 else st.text_input("Call To Action")

        # Resolution — dropdown/text
        res_opts = [""] + options_for(resolution_fid) if resolution_fid else [""]
        resolution = st.selectbox(label_for(resolution_fid, "Resolution"), res_opts) if resolution_fid and len(
            res_opts) > 1 else st.text_input("Resolution")

    # Escalate To — dropdown/text (full width)
    esc_opts = [""] + options_for(escalate_fid) if escalate_fid else [""]
    escalate_to = st.selectbox(label_for(escalate_fid, "Escalate To"), esc_opts) if escalate_fid and len(
        esc_opts) > 1 else st.text_input("Escalate To")

    submitted = st.form_submit_button("📨 Create Ticket")

# -----------------------------------------------------
# Submit handler
# -----------------------------------------------------
if submitted:
    # Required checks
    if not subject or not description or not (client or client_fid):
        st.error("Please fill all required fields (Subject, Description, Client).")
        st.stop()

    # Build ticket payload
    ticket_payload = {
        "subject": subject,
        "description": description,
        "tags": tags,
        "client": client.strip() if isinstance(client, str) else client,
        "phone_number": phone_number.strip(),
        "attack_vector": attack_vector.strip() if isinstance(attack_vector, str) else attack_vector,
        "call_to_action": call_to_action.strip() if isinstance(call_to_action, str) else call_to_action,
        "sources": sources.strip() if isinstance(sources, str) else sources,
        "resolution": resolution.strip() if isinstance(resolution, str) else resolution,
        "escalate_to": escalate_to.strip() if isinstance(escalate_to, str) else escalate_to,
    }

    # Check for duplicate phone number BEFORE creating ticket
    if phone_number and phone_number.strip():
        st.info(f"🔍 Checking for duplicates with phone: **{phone_number.strip()}**")
        st.info(f"📍 Phone field ID: **{zendesk_config.get('custom_fields', {}).get('phone_number_field_id')}**")

        with st.spinner("Checking for duplicate phone numbers..."):
            duplicate_check = check_phone_duplicate_via_middleware(phone_number.strip())

        # If duplicates found or error, store data and show warning
        if duplicate_check.get("error") or duplicate_check.get("exists"):
            st.session_state["pending_ticket_data"] = ticket_payload
            st.session_state["duplicate_check_result"] = duplicate_check
            st.session_state["show_duplicate_warning"] = True
            st.rerun()
        else:
            # No duplicates, create ticket directly
            create_ticket_flow(ticket_payload, zendesk_config)
    else:
        # No phone number, create ticket directly
        create_ticket_flow(ticket_payload, zendesk_config)

# =============================================================================
# Ticket List Widget with Pagination
# =============================================================================

st.markdown("---")
st.subheader("📋 Recent Tickets")

# Add filters
col1, col2, col3 = st.columns([2, 2, 1])

with col1:
    status_filter = st.selectbox(
        "Filter by Status",
        ["All", "new", "open", "pending", "solved", "closed"],
        key="status_filter"
    )

with col2:
    page_size = st.selectbox(
        "Tickets per page",
        [10, 25, 50, 100],
        index=0,
        key="page_size"
    )

with col3:
    if st.button("🔄 Refresh", key="refresh_tickets"):
        st.rerun()

# Initialize session state
if "current_page" not in st.session_state:
    st.session_state["current_page"] = 1

if "last_status_filter" not in st.session_state:
    st.session_state["last_status_filter"] = "All"

if "last_page_size" not in st.session_state:
    st.session_state["last_page_size"] = 10

# Reset to page 1 when filters change
if status_filter != st.session_state["last_status_filter"]:
    st.session_state["current_page"] = 1
    st.session_state["last_status_filter"] = status_filter

if page_size != st.session_state["last_page_size"]:
    st.session_state["current_page"] = 1
    st.session_state["last_page_size"] = page_size


def fetch_tickets(page: int, page_size: int, status: str = None):
    """Fetch tickets from middleware"""
    try:
        params = {
            "page": page,
            "page_size": page_size
        }
        if status and status != "All":
            params["status"] = status

        resp = requests.get(
            f"{MIDDLEWARE_URL}/mfl/tickets",
            params=params,
            timeout=30
        )

        if resp.status_code == 200:
            return resp.json()
        else:
            st.error(f"Failed to fetch tickets: {resp.status_code}")
            return {"success": False, "tickets": [], "total": 0}
    except Exception as e:
        st.error(f"Error fetching tickets: {e}")
        return {"success": False, "tickets": [], "total": 0}


# Fetch tickets
with st.spinner("Loading tickets..."):
    status_param = None if status_filter == "All" else status_filter
    ticket_data = fetch_tickets(
        page=st.session_state["current_page"],
        page_size=page_size,
        status=status_param
    )

if ticket_data.get("success"):
    tickets = ticket_data.get("tickets", [])
    total = ticket_data.get("total", 0)
    current_page = st.session_state["current_page"]

    if tickets:
        # Status emoji mapping
        status_emojis = {
            'new': '🆕',
            'open': '📂',
            'pending': '⏳',
            'solved': '✅',
            'closed': '🔒',
            'on-hold': '⏸️'
        }

        # Create formatted data for display
        display_data = []
        for ticket in tickets:
            # Format dates
            try:
                created = datetime.fromisoformat(ticket['created_at'].replace('Z', '+00:00'))
                updated = datetime.fromisoformat(ticket['updated_at'].replace('Z', '+00:00'))
                created_str = created.strftime("%Y-%m-%d %H:%M:%S")
                updated_str = updated.strftime("%Y-%m-%d %H:%M:%S")
            except:
                created_str = ticket.get('created_at', 'N/A')
                updated_str = ticket.get('updated_at', 'N/A')

            status = ticket.get('status', 'unknown')
            status_emoji = status_emojis.get(status, '❓')

            display_data.append({
                "Ticket #": ticket['id'],
                "Phone Number": ticket.get('phone_number', 'N/A'),
                "Status": f"{status_emoji} {status.title()}",
                "Created": created_str,
                "Updated": updated_str,
            })

        # Display as dataframe
        import pandas as pd

        df = pd.DataFrame(display_data)

        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
            height=400
        )

        # Add links below table
        with st.expander("🔗 View Tickets in Zendesk"):
            for ticket in tickets:
                st.markdown(f"- [Ticket #{ticket['id']}]({ticket['url']}) - {ticket.get('subject', 'N/A')}")

        # Pagination controls
        st.markdown("---")

        total_pages = max(1, (total + page_size - 1) // page_size)

        col1, col2, col3, col4, col5 = st.columns([1, 1, 2, 1, 1])

        with col1:
            if st.button("⏮️ First", disabled=(current_page == 1), key="btn_first"):
                st.session_state["current_page"] = 1
                st.rerun()

        with col2:
            if st.button("◀️ Prev", disabled=(current_page == 1), key="btn_prev"):
                st.session_state["current_page"] = max(1, current_page - 1)
                st.rerun()

        with col3:
            # Page selector
            new_page = st.number_input(
                f"Page (1-{total_pages})",
                min_value=1,
                max_value=total_pages,
                value=current_page,
                step=1,
                key="page_selector",
                label_visibility="collapsed"
            )

            # Auto-navigate if page changed
            if new_page != current_page:
                st.session_state["current_page"] = new_page
                st.rerun()

            st.caption(f"of {total_pages} pages • {total} total tickets")

        with col4:
            if st.button("Next ▶️", disabled=(current_page >= total_pages), key="btn_next"):
                st.session_state["current_page"] = min(total_pages, current_page + 1)
                st.rerun()

        with col5:
            if st.button("Last ⏭️", disabled=(current_page >= total_pages), key="btn_last"):
                st.session_state["current_page"] = total_pages
                st.rerun()

        # Show current range
        start_idx = (current_page - 1) * page_size + 1
        end_idx = min(current_page * page_size, total)
        st.info(f"📄 Showing tickets {start_idx}-{end_idx} of {total}")

    else:
        st.info("No tickets found matching the selected filters.")
else:
    st.error(f"Failed to load tickets: {ticket_data.get('error', 'Unknown error')}")


# -----------------------------------------------------
# Ticket Status Monitor (identical macro automation)
# -----------------------------------------------------
if "ticket_id" in st.session_state:
    st.markdown("---")
    st.subheader(f"📡 Ticket Status Monitor — #{st.session_state['ticket_id']}")

    ticket_id = st.session_state["ticket_id"]
    last_status = st.session_state.get("last_status", "unknown")

    with st.spinner("Fetching current status..."):
        ticket_data = get_ticket_status(ticket_id, zendesk_config)
        if "ticket" in ticket_data:
            current_status = ticket_data["ticket"].get("status", "unknown")
            created_at = ticket_data["ticket"].get("created_at")
            updated_at = ticket_data["ticket"].get("updated_at")
            subject_display = ticket_data["ticket"].get("subject", "N/A")
        else:
            st.error(f"Failed to fetch status: {ticket_data.get('error')}")
            st.stop()

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Status", current_status.upper())
    col2.metric("Created", created_at or "N/A")
    col3.metric("Updated", updated_at or "N/A")
    col4.metric("Ticket", f"#{ticket_id}")

    st.info(f"**Subject:** {subject_display}")

    # Auto-apply macro on status change
    if current_status != last_status:
        st.warning(f"🔄 Status changed: {last_status} → {current_status}")
        for key, macro in MACRO_CONFIG.items():
            if current_status == macro["trigger_status"]:
                with st.spinner(f"Applying macro: {macro['name']}"):
                    res = update_ticket_with_macro(ticket_id, macro["id"], zendesk_config)
                    if res.get("success"):
                        st.success(f"✅ Applied macro: {macro['name']}")
                        st.session_state["last_status"] = res.get("new_status", current_status)
                    else:
                        st.error(f"❌ Macro failed: {res.get('error')}")

    # Show latest public comment/email
    comments = get_ticket_comments(ticket_id, zendesk_config)
    if comments:
        last_comment = [c for c in comments if c.get("public", True)][-1]
        st.markdown("### 📧 Latest Comment")
        st.text_area("Latest Message", last_comment.get("body", ""), height=200, disabled=True)

    st.caption(f"Auto-refreshing every {STATUS_POLLING_INTERVAL} seconds...")

    col1, col2 = st.columns(2)
    if col1.button("🔄 Refresh Now"):
        st.rerun()
    if col2.button("⏹ Stop Monitoring"):
        st.session_state.clear()
        st.rerun()

    time.sleep(STATUS_POLLING_INTERVAL)
    st.rerun()