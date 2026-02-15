import uno
import unohelper
import json
import urllib.request
import os

from org.extension.localwriter.PromptFunction import XPromptFunction
from llm import build_api_request, make_ssl_context


class PromptFunction(unohelper.Base, XPromptFunction):
    def __init__(self, ctx):
        self.ctx = ctx

    def getProgrammaticFunctionName(self, aDisplayName):
        if aDisplayName == "PROMPT":
            return "prompt"
        return ""

    def getDisplayFunctionName(self, aProgrammaticName):
        if aProgrammaticName == "prompt":
            return "PROMPT"
        return ""

    def getFunctionDescription(self, aProgrammaticName):
        if aProgrammaticName == "prompt":
            return "Generates text using an LLM."
        return ""

    def getArgumentDescription(self, aProgrammaticName, nArgument):
        if aProgrammaticName == "prompt":
            if nArgument == 0:
                return "The prompt to send to the LLM."
        return ""

    def getArgumentName(self, aProgrammaticName, nArgument):
        if aProgrammaticName == "prompt":
            if nArgument == 0:
                return "message"
        return ""

    def hasFunctionWizard(self, aProgrammaticName):
        return True

    def getArgumentCount(self, aProgrammaticName):
        if aProgrammaticName == "prompt":
            return 1
        return 0

    def getArgumentIsOptional(self, aProgrammaticName, nArgument):
        return False

    def getProgrammaticCategoryName(self, aProgrammaticName):
        return "Add-In"

    def getDisplayCategoryName(self, aProgrammaticName):
        return "Add-In"

    def getLocale(self):
        return uno.createUnoStruct("com.sun.star.lang.Locale", "en", "US", "")

    def setLocale(self, locale):
        pass

    def load(self, xSomething):
        pass

    def unload(self):
        pass

    def prompt(self, message):
        try:
            endpoint = str(self.get_config("endpoint", "http://localhost:11434"))
            api_key = str(self.get_config("api_key", ""))
            api_type = str(self.get_config("api_type", "completions")).lower()
            model = str(self.get_config("model", ""))
            is_owui = self.get_config("is_openwebui", False)
            openai_compat = self.get_config("openai_compatibility", False)
            system_prompt = str(self.get_config("extend_selection_system_prompt", ""))
            max_tokens = self.get_config("extend_selection_max_tokens", 70)

            request = build_api_request(
                message, endpoint, api_key, api_type, model,
                is_owui, openai_compat, system_prompt, int(max_tokens))

            # Override stream to False — Calc needs the full response at once
            body = json.loads(request.data.decode('utf-8'))
            body['stream'] = False
            request.data = json.dumps(body).encode('utf-8')

            disable_ssl = self.get_config("disable_ssl_verification", False)
            ssl_ctx = make_ssl_context(disable_ssl)

            with urllib.request.urlopen(request, context=ssl_ctx) as response:
                response_json = json.loads(response.read().decode('utf-8'))
                if api_type == "chat":
                    return response_json["choices"][0]["message"]["content"]
                else:
                    return response_json["choices"][0]["text"]

        except urllib.error.HTTPError as e:
            error_body = e.read().decode('utf-8')
            return f"HTTP Error {e.code}: {error_body}"
        except urllib.error.URLError as e:
            return f"Connection error: {e.reason}"
        except Exception as e:
            return f"Error: {e}"

    def get_config(self, key, default):
        name_file = "localwriter.json"
        path_settings = self.ctx.getServiceManager().createInstanceWithContext(
            'com.sun.star.util.PathSettings', self.ctx)
        user_config_path = getattr(path_settings, "UserConfig")
        if user_config_path.startswith('file://'):
            user_config_path = str(uno.fileUrlToSystemPath(user_config_path))
        config_file_path = os.path.join(user_config_path, name_file)
        if not os.path.exists(config_file_path):
            return default
        try:
            with open(config_file_path, 'r') as file:
                config_data = json.load(file)
        except (IOError, json.JSONDecodeError):
            return default
        return config_data.get(key, default)

    def getImplementationName(self):
        return "org.extension.localwriter.PromptFunction"

    def supportsService(self, name):
        return name in self.getSupportedServiceNames()

    def getSupportedServiceNames(self):
        return ("com.sun.star.sheet.AddIn",)


g_ImplementationHelper = unohelper.ImplementationHelper()
g_ImplementationHelper.addImplementation(
    PromptFunction,
    "org.extension.localwriter.PromptFunction",
    ("com.sun.star.sheet.AddIn",),
)
