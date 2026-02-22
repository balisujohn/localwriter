import sys
import os

# Ensure extension directory is on path so core can be imported
_ext_dir = os.path.dirname(os.path.abspath(__file__))
if _ext_dir not in sys.path:
    sys.path.insert(0, _ext_dir)

import uno
import unohelper

from org.extension.localwriter.PromptFunction import XPromptFunction
from core.config import get_config, get_api_config
from core.api import LlmClient, format_error_for_display


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
            system_prompt = str(get_config(self.ctx, "extend_selection_system_prompt", ""))
            max_tokens = get_config(self.ctx, "extend_selection_max_tokens", 70)
            try:
                max_tokens = int(max_tokens)
            except (TypeError, ValueError):
                max_tokens = 70

            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": message})

            config = get_api_config(self.ctx)
            client = LlmClient(config, self.ctx)
            return client.chat_completion_sync(messages, max_tokens=max_tokens)

        except Exception as e:
            return format_error_for_display(e)

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
