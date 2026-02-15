import sys
import unohelper
import officehelper
import json
import urllib.request
import urllib.parse
import ssl
from com.sun.star.task import XJobExecutor
from com.sun.star.awt import MessageBoxButtons as MSG_BUTTONS
import uno
import os
import logging
import re

from com.sun.star.beans import PropertyValue
from com.sun.star.container import XNamed

from llm import (as_bool, is_openai_compatible, build_api_request,
                 extract_content, make_ssl_context, stream_response)


_debug_logging_enabled = False

def log_to_file(message):
    if not _debug_logging_enabled:
        return
    log_dir = os.path.join(os.path.expanduser('~'), '.localwriter')
    os.makedirs(log_dir, exist_ok=True)
    log_file_path = os.path.join(log_dir, 'log.txt')
    logging.basicConfig(filename=log_file_path, level=logging.INFO, format='%(asctime)s - %(message)s')
    logging.info(message)


# The MainJob is a UNO component derived from unohelper.Base class
# and also the XJobExecutor, the implemented interface
class MainJob(unohelper.Base, XJobExecutor):
    def __init__(self, ctx):
        self.ctx = ctx
        # handling different situations (inside LibreOffice or other process)
        try:
            self.sm = ctx.getServiceManager()
            self.desktop = XSCRIPTCONTEXT.getDesktop()
            self.document = XSCRIPTCONTEXT.getDocument()
        except NameError:
            self.sm = ctx.ServiceManager
            self.desktop = self.ctx.getServiceManager().createInstanceWithContext(
                "com.sun.star.frame.Desktop", self.ctx)
    

    def get_config(self,key,default):
  
        name_file ="localwriter.json"
        #path_settings = create_instance('com.sun.star.util.PathSettings')
        
        
        path_settings = self.sm.createInstanceWithContext('com.sun.star.util.PathSettings', self.ctx)

        user_config_path = getattr(path_settings, "UserConfig")

        if user_config_path.startswith('file://'):
            user_config_path = str(uno.fileUrlToSystemPath(user_config_path))
        
        # Ensure the path ends with the filename
        config_file_path = os.path.join(user_config_path, name_file)

        # Check if the file exists
        if not os.path.exists(config_file_path):
            return default

        # Try to load the JSON content from the file
        try:
            with open(config_file_path, 'r') as file:
                config_data = json.load(file)
        except (IOError, json.JSONDecodeError):
            return default

        # Return the value corresponding to the key, or the default value if the key is not found
        return config_data.get(key, default)

    def set_config(self, key, value):
        name_file = "localwriter.json"
        
        path_settings = self.sm.createInstanceWithContext('com.sun.star.util.PathSettings', self.ctx)
        user_config_path = getattr(path_settings, "UserConfig")

        if user_config_path.startswith('file://'):
            user_config_path = str(uno.fileUrlToSystemPath(user_config_path))

        # Ensure the path ends with the filename
        config_file_path = os.path.join(user_config_path, name_file)

        # Load existing configuration if the file exists
        if os.path.exists(config_file_path):
            try:
                with open(config_file_path, 'r') as file:
                    config_data = json.load(file)
            except (IOError, json.JSONDecodeError):
                config_data = {}
        else:
            config_data = {}

        # Update the configuration with the new key-value pair
        config_data[key] = value

        # Write the updated configuration back to the file
        try:
            with open(config_file_path, 'w') as file:
                json.dump(config_data, file, indent=4)
        except IOError as e:
            # Handle potential IO errors (optional)
            print(f"Error writing to {config_file_path}: {e}")

    def _as_bool(self, value):
        return as_bool(value)

    def _is_openai_compatible(self):
        endpoint = str(self.get_config("endpoint", "http://localhost:11434"))
        compatibility_flag = self.get_config("openai_compatibility", False)
        return is_openai_compatible(endpoint, compatibility_flag)

    def make_api_request(self, prompt, system_prompt="", max_tokens=70, api_type=None):
        endpoint = str(self.get_config("endpoint", "http://localhost:11434"))
        api_key = str(self.get_config("api_key", ""))
        if api_type is None:
            api_type = str(self.get_config("api_type", "completions")).lower()
        model = str(self.get_config("model", ""))
        is_owui = self.get_config("is_openwebui", False)
        openai_compat = self.get_config("openai_compatibility", False)
        return build_api_request(prompt, endpoint, api_key, api_type, model,
                                 is_owui, openai_compat, system_prompt, max_tokens,
                                 log_fn=log_to_file)

    def extract_content_from_response(self, chunk, api_type="completions"):
        return extract_content(chunk, api_type)

    def get_ssl_context(self):
        disable = self.get_config("disable_ssl_verification", False)
        return make_ssl_context(disable)

    def stream_request(self, request, api_type, append_callback):
        toolkit = self.ctx.getServiceManager().createInstanceWithContext(
            "com.sun.star.awt.Toolkit", self.ctx
        )
        ssl_ctx = self.get_ssl_context()
        stream_response(request, api_type, ssl_ctx, append_callback,
                        on_idle=toolkit.processEventsToIdle, log_fn=log_to_file)

    #retrieved from https://wiki.documentfoundation.org/Macros/General/IO_to_Screen
    #License: Creative Commons Attribution-ShareAlike 3.0 Unported License,
    #License: The Document Foundation  https://creativecommons.org/licenses/by-sa/3.0/
    #begin sharealike section 
    def input_box(self,message, title="", default="", x=None, y=None):
        """ Shows dialog with input box.
            @param message message to show on the dialog
            @param title window title
            @param default default value
            @param x optional dialog position in twips
            @param y optional dialog position in twips
            @return string if OK button pushed, otherwise zero length string
        """
        WIDTH = 600
        HORI_MARGIN = VERT_MARGIN = 8
        BUTTON_WIDTH = 100
        BUTTON_HEIGHT = 26
        HORI_SEP = VERT_SEP = 8
        LABEL_HEIGHT = BUTTON_HEIGHT * 2 + 5
        EDIT_HEIGHT = 24
        HEIGHT = VERT_MARGIN * 2 + LABEL_HEIGHT + VERT_SEP + EDIT_HEIGHT
        import uno
        from com.sun.star.awt.PosSize import POS, SIZE, POSSIZE
        from com.sun.star.awt.PushButtonType import OK, CANCEL
        from com.sun.star.util.MeasureUnit import TWIP
        ctx = uno.getComponentContext()
        def create(name):
            return ctx.getServiceManager().createInstanceWithContext(name, ctx)
        dialog = create("com.sun.star.awt.UnoControlDialog")
        dialog_model = create("com.sun.star.awt.UnoControlDialogModel")
        dialog.setModel(dialog_model)
        dialog.setVisible(False)
        dialog.setTitle(title)
        dialog.setPosSize(0, 0, WIDTH, HEIGHT, SIZE)
        def add(name, type, x_, y_, width_, height_, props):
            model = dialog_model.createInstance("com.sun.star.awt.UnoControl" + type + "Model")
            dialog_model.insertByName(name, model)
            control = dialog.getControl(name)
            control.setPosSize(x_, y_, width_, height_, POSSIZE)
            for key, value in props.items():
                setattr(model, key, value)
        label_width = WIDTH - BUTTON_WIDTH - HORI_SEP - HORI_MARGIN * 2
        add("label", "FixedText", HORI_MARGIN, VERT_MARGIN, label_width, LABEL_HEIGHT, 
            {"Label": str(message), "NoLabel": True})
        add("btn_ok", "Button", HORI_MARGIN + label_width + HORI_SEP, VERT_MARGIN, 
                BUTTON_WIDTH, BUTTON_HEIGHT, {"PushButtonType": OK, "DefaultButton": True})
        add("edit", "Edit", HORI_MARGIN, LABEL_HEIGHT + VERT_MARGIN + VERT_SEP, 
                WIDTH - HORI_MARGIN * 2, EDIT_HEIGHT, {"Text": str(default)})
        frame = create("com.sun.star.frame.Desktop").getCurrentFrame()
        window = frame.getContainerWindow() if frame else None
        dialog.createPeer(create("com.sun.star.awt.Toolkit"), window)
        if not x is None and not y is None:
            ps = dialog.convertSizeToPixel(uno.createUnoStruct("com.sun.star.awt.Size", x, y), TWIP)
            _x, _y = ps.Width, ps.Height
        elif window:
            ps = window.getPosSize()
            _x = ps.Width / 2 - WIDTH / 2
            _y = ps.Height / 2 - HEIGHT / 2
        dialog.setPosSize(_x, _y, 0, 0, POS)
        edit = dialog.getControl("edit")
        edit.setSelection(uno.createUnoStruct("com.sun.star.awt.Selection", 0, len(str(default))))
        edit.setFocus()
        ret = edit.getModel().Text if dialog.execute() else ""
        dialog.dispose()
        return ret

    # Backend presets: (name, api_type, is_openwebui, openai_compat, default_endpoint)
    BACKEND_PRESETS = [
        ("Ollama",               "completions", False, False, "http://localhost:11434"),
        ("LM Studio",           "completions", False, False, "http://localhost:1234"),
        ("text-generation-webui","completions", False, False, "http://localhost:5000"),
        ("OpenAI",               "chat",        False, False, "https://api.openai.com"),
        ("OpenWebUI",            "chat",        True,  False, "http://localhost:3000"),
        ("Custom",               None,          None,  None,  None),
    ]

    def _detect_backend(self):
        api_type = str(self.get_config("api_type", "completions")).lower()
        is_owui = self._as_bool(self.get_config("is_openwebui", False))
        endpoint = str(self.get_config("endpoint", "http://localhost:11434"))
        if is_owui:
            return 4  # OpenWebUI
        if api_type == "chat":
            return 3  # OpenAI
        if ":1234" in endpoint:
            return 1  # LM Studio
        if ":5000" in endpoint:
            return 2  # text-generation-webui
        return 0  # Ollama

    def _read_dialog_config(self, controls):
        """Read all control values and return a config dict."""
        result = {}
        # Backend preset -> api_type, is_openwebui, openai_compatibility
        sel = controls["backend"].getModel().SelectedItems
        backend_idx = sel[0] if sel else 0
        preset = self.BACKEND_PRESETS[backend_idx]
        if preset[1] is not None:  # not Custom
            result["api_type"] = preset[1]
            result["is_openwebui"] = preset[2]
            result["openai_compatibility"] = preset[3]
        else:
            result["api_type"] = str(self.get_config("api_type", "completions"))
            result["is_openwebui"] = self._as_bool(self.get_config("is_openwebui", False))
            result["openai_compatibility"] = self._as_bool(
                self.get_config("openai_compatibility", False))
        # Text fields
        for name in ["endpoint", "model", "api_key",
                     "extend_selection_system_prompt", "edit_selection_system_prompt"]:
            result[name] = controls[name].getModel().Text
        # Checkboxes
        for name in ["disable_ssl_verification", "debug_logging"]:
            result[name] = controls[name].getModel().State == 1
        # Numeric fields
        for name in ["extend_selection_max_tokens", "edit_selection_max_new_tokens"]:
            text = controls[name].getModel().Text
            result[name] = int(text) if text.isdigit() else 0
        return result

    def settings_box(self, title="", x=None, y=None):
        """ Settings dialog with backend preset, checkboxes, and JSON preview """
        WIDTH = 600
        HORI_MARGIN = VERT_MARGIN = 8
        BUTTON_WIDTH = 100
        BUTTON_HEIGHT = 26
        HORI_SEP = 8
        VERT_SEP = 4
        LABEL_HEIGHT = BUTTON_HEIGHT + 5
        EDIT_HEIGHT = 24
        CHECKBOX_HEIGHT = 20
        JSON_HEIGHT = 120

        import uno
        from com.sun.star.awt.PosSize import POS, SIZE, POSSIZE
        from com.sun.star.awt.PushButtonType import OK, CANCEL
        from com.sun.star.util.MeasureUnit import TWIP
        from com.sun.star.awt import XActionListener, XItemListener
        ctx = uno.getComponentContext()

        def create(name):
            return ctx.getServiceManager().createInstanceWithContext(name, ctx)

        dialog = create("com.sun.star.awt.UnoControlDialog")
        dialog_model = create("com.sun.star.awt.UnoControlDialogModel")
        dialog.setModel(dialog_model)
        dialog.setVisible(False)
        dialog.setTitle(title)

        def add(name, ctrl_type, x_, y_, width_, height_, props):
            model = dialog_model.createInstance(
                "com.sun.star.awt.UnoControl" + ctrl_type + "Model")
            dialog_model.insertByName(name, model)
            control = dialog.getControl(name)
            control.setPosSize(x_, y_, width_, height_, POSSIZE)
            for key, value in props.items():
                setattr(model, key, value)
            return control

        label_width = WIDTH - BUTTON_WIDTH - HORI_SEP - HORI_MARGIN * 2
        edit_width = WIDTH - HORI_MARGIN * 2
        controls = {}
        y = VERT_MARGIN

        # --- OK button (top-right) ---
        add("btn_ok", "Button", HORI_MARGIN + label_width + HORI_SEP, y,
            BUTTON_WIDTH, BUTTON_HEIGHT, {"PushButtonType": OK, "DefaultButton": True})

        # --- Backend dropdown ---
        add("label_backend", "FixedText", HORI_MARGIN, y, label_width, LABEL_HEIGHT,
            {"Label": "Backend:", "NoLabel": True})
        y += LABEL_HEIGHT + VERT_SEP
        backend_names = tuple(p[0] for p in self.BACKEND_PRESETS)
        current_backend = self._detect_backend()
        controls["backend"] = add("list_backend", "ListBox", HORI_MARGIN, y,
            edit_width, EDIT_HEIGHT,
            {"Dropdown": True, "StringItemList": backend_names,
             "SelectedItems": (current_backend,), "LineCount": 6})
        y += EDIT_HEIGHT + VERT_SEP

        # --- Text fields: endpoint, model, api_key ---
        text_fields = [
            ("endpoint", "Endpoint URL/Port:",
             str(self.get_config("endpoint", "http://localhost:11434"))),
            ("model", "Model:",
             str(self.get_config("model", ""))),
            ("api_key", "API Key:",
             str(self.get_config("api_key", ""))),
        ]
        for name, label, value in text_fields:
            add(f"label_{name}", "FixedText", HORI_MARGIN, y, label_width, LABEL_HEIGHT,
                {"Label": label, "NoLabel": True})
            y += LABEL_HEIGHT + VERT_SEP
            controls[name] = add(f"edit_{name}", "Edit", HORI_MARGIN, y,
                edit_width, EDIT_HEIGHT, {"Text": value})
            y += EDIT_HEIGHT + VERT_SEP

        # --- Checkboxes ---
        disable_ssl = self._as_bool(self.get_config("disable_ssl_verification", False))
        debug_log = self._as_bool(self.get_config("debug_logging", False))
        checkbox_fields = [
            ("disable_ssl_verification", "Disable SSL verification (exposes API keys to interception)", disable_ssl),
            ("debug_logging", "Enable debug logging to ~~/.localwriter/log.txt", debug_log),
        ]
        for name, label, checked in checkbox_fields:
            controls[name] = add(f"cb_{name}", "CheckBox", HORI_MARGIN, y,
                edit_width, CHECKBOX_HEIGHT,
                {"Label": label, "State": 1 if checked else 0})
            y += CHECKBOX_HEIGHT + VERT_SEP

        # --- Numeric fields ---
        int_fields = [
            ("extend_selection_max_tokens", "Extend Selection Max Tokens:",
             str(self.get_config("extend_selection_max_tokens", "70"))),
            ("edit_selection_max_new_tokens", "Edit Selection Max New Tokens:",
             str(self.get_config("edit_selection_max_new_tokens", "0"))),
        ]
        for name, label, value in int_fields:
            add(f"label_{name}", "FixedText", HORI_MARGIN, y, label_width, LABEL_HEIGHT,
                {"Label": label, "NoLabel": True})
            y += LABEL_HEIGHT + VERT_SEP
            controls[name] = add(f"edit_{name}", "Edit", HORI_MARGIN, y,
                edit_width, EDIT_HEIGHT, {"Text": value})
            y += EDIT_HEIGHT + VERT_SEP

        # --- System prompt fields ---
        prompt_fields = [
            ("extend_selection_system_prompt", "Extend Selection System Prompt:",
             str(self.get_config("extend_selection_system_prompt", ""))),
            ("edit_selection_system_prompt", "Edit Selection System Prompt:",
             str(self.get_config("edit_selection_system_prompt", ""))),
        ]
        for name, label, value in prompt_fields:
            add(f"label_{name}", "FixedText", HORI_MARGIN, y, label_width, LABEL_HEIGHT,
                {"Label": label, "NoLabel": True})
            y += LABEL_HEIGHT + VERT_SEP
            controls[name] = add(f"edit_{name}", "Edit", HORI_MARGIN, y,
                edit_width, EDIT_HEIGHT, {"Text": value})
            y += EDIT_HEIGHT + VERT_SEP

        # --- JSON preview ---
        add("btn_refresh", "Button", HORI_MARGIN, y, BUTTON_WIDTH, BUTTON_HEIGHT,
            {"Label": "Refresh"})
        add("label_json", "FixedText", HORI_MARGIN + BUTTON_WIDTH + HORI_SEP, y,
            label_width - BUTTON_WIDTH - HORI_SEP, LABEL_HEIGHT,
            {"Label": "Configuration preview:", "NoLabel": True})
        y += LABEL_HEIGHT + VERT_SEP
        json_ctrl = add("edit_json", "Edit", HORI_MARGIN, y, edit_width, JSON_HEIGHT,
            {"Text": "", "ReadOnly": True, "MultiLine": True, "VScroll": True})
        y += JSON_HEIGHT + VERT_MARGIN

        # --- Size and position ---
        dialog_height = y
        dialog.setPosSize(0, 0, WIDTH, dialog_height, SIZE)
        frame = create("com.sun.star.frame.Desktop").getCurrentFrame()
        window = frame.getContainerWindow() if frame else None
        dialog.createPeer(create("com.sun.star.awt.Toolkit"), window)
        if x is not None and y is not None:
            ps = dialog.convertSizeToPixel(
                uno.createUnoStruct("com.sun.star.awt.Size", x, y), TWIP)
            _x, _y = ps.Width, ps.Height
        elif window:
            ps = window.getPosSize()
            _x = ps.Width / 2 - WIDTH / 2
            _y = ps.Height / 2 - dialog_height / 2
        dialog.setPosSize(_x, _y, 0, 0, POS)

        # --- Update JSON preview from current control values ---
        settings_box_self = self

        def update_json_preview():
            config = settings_box_self._read_dialog_config(controls)
            json_ctrl.getModel().Text = json.dumps(config, indent=2)

        # Show initial JSON preview
        update_json_preview()

        # --- Backend change listener: auto-fill endpoint ---
        presets = self.BACKEND_PRESETS

        class BackendListener(unohelper.Base, XItemListener):
            def itemStateChanged(self, event):
                sel = controls["backend"].getModel().SelectedItems
                if not sel:
                    return
                idx = sel[0]
                preset = presets[idx]
                if preset[4] is not None:  # has default endpoint
                    controls["endpoint"].getModel().Text = preset[4]
                update_json_preview()

            def disposing(self, source):
                pass

        controls["backend"].addItemListener(BackendListener())

        # --- Refresh button listener: update preview from current controls ---
        class RefreshListener(unohelper.Base, XActionListener):
            def actionPerformed(self, event):
                update_json_preview()

            def disposing(self, source):
                pass

        dialog.getControl("btn_refresh").addActionListener(RefreshListener())

        controls["endpoint"].setFocus()

        # --- Execute and collect results ---
        if dialog.execute():
            result = self._read_dialog_config(controls)
        else:
            result = {}

        dialog.dispose()
        return result
    #end sharealike section

    def _save_settings(self, result):
        for key, value in result.items():
            if key == "endpoint" and not str(value).startswith("http"):
                continue
            if key == "api_type":
                value = str(value).strip().lower()
                if value not in ("chat", "completions"):
                    value = "completions"
            self.set_config(key, value)

    def trigger(self, args):
        global _debug_logging_enabled
        _debug_logging_enabled = self._as_bool(self.get_config("debug_logging", False))

        desktop = self.ctx.ServiceManager.createInstanceWithContext(
            "com.sun.star.frame.Desktop", self.ctx)
        model = desktop.getCurrentComponent()

        if hasattr(model, "Text"):
            text = model.Text
            selection = model.CurrentController.getSelection()
            text_range = selection.getByIndex(0)

            
            if args == "ExtendSelection":
                # Access the current selection
                if len(text_range.getString()) > 0:
                    try:
                        # Prepare request using the new unified method
                        system_prompt = self.get_config("extend_selection_system_prompt", "")
                        prompt = text_range.getString()
                        max_tokens = self.get_config("extend_selection_max_tokens", 70)
                        
                        api_type = str(self.get_config("api_type", "completions")).lower()
                        request = self.make_api_request(prompt, system_prompt, max_tokens, api_type=api_type)

                        def append_text(chunk_text):
                            text_range.setString(text_range.getString() + chunk_text)

                        self.stream_request(request, api_type, append_text)
                                      
                    except Exception as e:
                        text_range = selection.getByIndex(0)
                        # Append the user input to the selected text
                        text_range.setString(text_range.getString() + ": " + str(e))

            elif args == "EditSelection":
                # Access the current selection
                try:
                    user_input = self.input_box("Please enter edit instructions!", "Input", "")
                    
                    # Prepare the prompt for editing
                    prompt = "ORIGINAL VERSION:\n" + text_range.getString() + "\n Below is an edited version according to the following instructions. There are no comments in the edited version. The edited version is followed by the end of the document. The original version will be edited as follows to create the edited version:\n" + user_input + "\nEDITED VERSION:\n"
                    
                    system_prompt = self.get_config("edit_selection_system_prompt", "")
                    max_tokens = len(text_range.getString()) + self.get_config("edit_selection_max_new_tokens", 0)
                    
                    api_type = str(self.get_config("api_type", "completions")).lower()
                    request = self.make_api_request(prompt, system_prompt, max_tokens, api_type=api_type)
                    
                    text_range.setString("")

                    def append_text(chunk_text):
                        text_range.setString(text_range.getString() + chunk_text)

                    self.stream_request(request, api_type, append_text)

                except Exception as e:
                    text_range = selection.getByIndex(0)
                    # Append the user input to the selected text
                    text_range.setString(text_range.getString() + ": " + str(e))
            
            elif args == "settings":
                try:
                    result = self.settings_box("Settings")
                    self._save_settings(result)
                except Exception as e:
                    text_range = selection.getByIndex(0)
                    text_range.setString(text_range.getString() + ":error: " + str(e))
        elif hasattr(model, "Sheets"):
            try:
                sheet = model.CurrentController.ActiveSheet
                selection = model.CurrentController.Selection

                if args == "settings":
                    try:
                        result = self.settings_box("Settings")
                        self._save_settings(result)
                    except Exception as e:
                        log_to_file(f"Calc settings error: {str(e)}")
                    return

                user_input = ""
                if args == "EditSelection":
                    user_input = self.input_box("Please enter edit instructions!", "Input", "")

                area = selection.getRangeAddress()
                start_row = area.StartRow
                end_row = area.EndRow
                start_col = area.StartColumn
                end_col = area.EndColumn

                col_range = range(start_col, end_col + 1)
                row_range = range(start_row, end_row + 1)

                api_type = str(self.get_config("api_type", "completions")).lower()
                extend_system_prompt = self.get_config("extend_selection_system_prompt", "")
                extend_max_tokens = self.get_config("extend_selection_max_tokens", 70)
                edit_system_prompt = self.get_config("edit_selection_system_prompt", "")
                edit_max_new_tokens = self.get_config("edit_selection_max_new_tokens", 0)
                try:
                    edit_max_new_tokens = int(edit_max_new_tokens)
                except (TypeError, ValueError):
                    edit_max_new_tokens = 0

                for row in row_range:
                    for col in col_range:
                        cell = sheet.getCellByPosition(col, row)

                        if args == "ExtendSelection":
                            cell_text = cell.getString()
                            if not cell_text:
                                continue
                            try:
                                request = self.make_api_request(cell_text, extend_system_prompt, extend_max_tokens, api_type=api_type)

                                def append_cell_text(chunk_text, target_cell=cell):
                                    target_cell.setString(target_cell.getString() + chunk_text)

                                self.stream_request(request, api_type, append_cell_text)
                            except Exception as e:
                                cell.setString(cell.getString() + ": " + str(e))
                        elif args == "EditSelection":
                            try:
                                prompt =  "ORIGINAL VERSION:\n" + cell.getString() + "\n Below is an edited version according to the following instructions. Don't waste time thinking, be as fast as you can. The edited text will be a shorter or longer version of the original text based on the instructions. There are no comments in the edited version. The edited version is followed by the end of the document. The original version will be edited as follows to create the edited version:\n" + user_input + "\nEDITED VERSION:\n"

                                max_tokens = len(cell.getString()) + edit_max_new_tokens
                                request = self.make_api_request(prompt, edit_system_prompt, max_tokens, api_type=api_type)

                                cell.setString("")

                                def append_edit_text(chunk_text, target_cell=cell):
                                    target_cell.setString(target_cell.getString() + chunk_text)

                                self.stream_request(request, api_type, append_edit_text)
                            except Exception as e:
                                cell.setString(cell.getString() + ": " + str(e))
            except Exception:
                pass
# Starting from Python IDE
def main():
    try:
        ctx = XSCRIPTCONTEXT
    except NameError:
        ctx = officehelper.bootstrap()
        if ctx is None:
            print("ERROR: Could not bootstrap default Office.")
            sys.exit(1)
    job = MainJob(ctx)
    job.trigger("hello")
# Starting from command line
if __name__ == "__main__":
    main()
# pythonloader loads a static g_ImplementationHelper variable
g_ImplementationHelper = unohelper.ImplementationHelper()
g_ImplementationHelper.addImplementation(
    MainJob,  # UNO object class
    "org.extension.sample.do",  # implementation name (customize for yourself)
    ("com.sun.star.task.Job",), )  # implemented services (only 1)
# vim: set shiftwidth=4 softtabstop=4 expandtab:
