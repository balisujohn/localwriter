import uno
import unohelper
import json
import urllib.request
import urllib.parse
import os
from com.sun.star.sheet import XAddIn

class PromptFunction(unohelper.Base, XAddIn):
    def __init__(self, ctx):
        self.ctx = ctx

    def getProgrammaticFuntionName(self, aDisplayName):
        if aDisplayName == "PROMPT":
            return "PROMPT"
        return ""

    def getDisplayFunctionName(self, aProgrammaticName):
        if aProgrammaticName == "PROMPT":
            return "PROMPT"
        return ""

    def getFunctionDescription(self, aProgrammaticName):
        if aProgrammaticName == "PROMPT":
            return "Generates text using an LLM."
        return ""

    def getArgumentDescription(self, aProgrammaticName, nArgument):
        if aProgrammaticName == "PROMPT":
            if nArgument == 0:
                return "The prompt to send to the LLM."
            elif nArgument == 1:
                return "The system prompt to use."
            elif nArgument == 2:
                return "The model to use."
            elif nArgument == 3:
                return "The maximum number of tokens to generate."
        return ""

    def hasFunctionWizard(self, aProgrammaticName):
        return True

    def getArgumentCount(self, aProgrammaticName):
        if aProgrammaticName == "PROMPT":
            return 4
        return 0

    def getArgumentIsOptional(self, aProgrammaticName, nArgument):
        if aProgrammaticName == "PROMPT":
            return nArgument > 0
        return False

    def getProgrammaticCategoryName(self, aProgrammaticName):
        return "Add-In"

    def getDisplayCategoryName(self, aProgrammaticName):
        return "Add-In"

    def getLocale(self):
        return self.ctx.ServiceManager.createInstance("com.sun.star.lang.Locale", ("en", "US", ""))

    def setLocale(self, locale):
        pass

    def load(self, xSomething):
        pass

    def unload(self):
        pass

    def invoke(self, aProgrammaticName, aArgumentList):
        if aProgrammaticName == "PROMPT":
            try:
                message = aArgumentList[0]
                system_prompt = aArgumentList[1] if len(aArgumentList) > 1 and aArgumentList[1] else self.get_config("extend_selection_system_prompt", "")
                model = aArgumentList[2] if len(aArgumentList) > 2 and aArgumentList[2] else self.get_config("model", "")
                max_tokens = aArgumentList[3] if len(aArgumentList) > 3 and aArgumentList[3] else self.get_config("extend_selection_max_tokens", 70)

                url = self.get_config("endpoint", "http://127.0.0.1:5000") + "/v1/completions"
                headers = {'Content-Type': 'application/json'}

                prompt = f"SYSTEM PROMPT\n{system_prompt}\nEND SYSTEM PROMPT\n{message}" if system_prompt else message

                data = {
                    'prompt': prompt,
                    'max_tokens': int(max_tokens),
                    'temperature': 1,
                    'top_p': 0.9,
                    'seed': 10
                }
                if model:
                    data["model"] = model

                json_data = json.dumps(data).encode('utf-8')
                request = urllib.request.Request(url, data=json_data, headers=headers, method='POST')

                with urllib.request.urlopen(request) as response:
                    response_data = response.read()
                    response_json = json.loads(response_data.decode('utf-8'))
                    return response_json["choices"][0]["text"]
            except Exception as e:
                return f"Error: {e}"
        return ""

    def get_config(self, key, default):
        # This is a simplified version of the get_config function from main.py
        # We will need to find a way to share this code.
        name_file = "localwriter.json"
        path_settings = self.ctx.ServiceManager.createInstanceWithContext('com.sun.star.util.PathSettings', self.ctx)
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

g_ImplementationHelper = unohelper.ImplementationHelper()
g_ImplementationHelper.addImplementation(
    PromptFunction,
    "org.extension.sample.PromptFunction",
    ("com.sun.star.sheet.AddIn",),
)
