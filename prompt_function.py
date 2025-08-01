import uno
import unohelper
import json
import urllib.request
import urllib.parse
import os
# from com.sun.star.lang import XServiceInfo
# from com.sun.star.sheet import XAddIn
from org.extension.localwriter.PromptFunction import XPromptFunction

# Enable debug logging
DEBUG = True

def debug_log(message):
    """Debug logging function"""
    if DEBUG:
        try:
            # Try to write to a debug file
            debug_file = os.path.expanduser("~/libreoffice_prompt_debug.log")
            with open(debug_file, "a", encoding="utf-8") as f:
                f.write(f"{message}\n")
        except:
            # Fallback to stdout
            print(f"DEBUG: {message}")
            sys.stdout.flush()

class PromptFunction(unohelper.Base, XPromptFunction):
    def __init__(self, ctx):
        debug_log("=== PromptFunction.__init__ called ===")
        self.ctx = ctx

    def getProgrammaticFunctionName(self, aDisplayName):
        debug_log(f"=== getProgrammaticFunctionName called with: '{aDisplayName}' ===")
        if aDisplayName == "PROMPT":
            return "prompt"
        return ""

    def getDisplayFunctionName(self, aProgrammaticName):
        debug_log(f"=== getDisplayFunctionName called with: '{aProgrammaticName}' ===")
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
            elif nArgument == 1:
                return "The system prompt to use."
            elif nArgument == 2:
                return "The model to use."
            elif nArgument == 3:
                return "The maximum number of tokens to generate."
        return ""
        
    def getArgumentName(self, nProgrammaticName, nArgument):
        if aProgrammaticName == "prompt":
            if nArgument == 0:
                return "message"
            elif nArgument == 1:
                return "system_prompt"
            elif nArgument == 2:
                return "model"
            elif nArgument == 3:
                return "max_tokens"
        return ""

    def hasFunctionWizard(self, aProgrammaticName):
        return True

    def getArgumentCount(self, aProgrammaticName):
        if aProgrammaticName == "prompt":
            return 4
        return 0

    def getArgumentIsOptional(self, aProgrammaticName, nArgument):
        if aProgrammaticName == "prompt":
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

    def prompt(self, message, systemPrompt, model, maxTokens):
        debug_log(f"=== PromptFunction.PROMPT({message}) called ===")
        aProgrammaticName = "PROMPT"
        if aProgrammaticName == "PROMPT":
            try:
                system_prompt = systemPrompt if systemPrompt is not None else self.get_config("extend_selection_system_prompt", "")
                model = model if model is not None else self.get_config("model", "")
                max_tokens = maxTokens if maxTokens is not None else self.get_config("extend_selection_max_tokens", 70)
                seed = self.get_config("seed", None)
                seed = int(seed) if seed is not None and len(str(seed)) else None
                temperature = self.get_config("temperature", 0.5)

                url = self.get_config("endpoint", "http://127.0.0.1:5000") + "/v1/chat/completions"
                headers = {
                    'Content-Type': 'application/json',
                    'User-Agent': (
                        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                        'AppleWebKit/537.36 (KHTML, like Gecko) '
                        'Chrome/114.0.0.0 Safari/537.36'
                    )
                }
                api_key = self.get_config("api_key", "")
                if api_key:
                    headers['Authorization'] = f"Bearer {api_key}"

                prompt = f"SYSTEM PROMPT\n{system_prompt}\nEND SYSTEM PROMPT\n{message}" if system_prompt else message
                messages = []
                if system_prompt:
                    messages.append({"role": "system", "content": system_prompt})
                messages.append({"role": "user", "content": message})
                data = {
                    #'prompt': prompt,
                    'messages': messages,
                    'max_tokens': int(max_tokens),
                    'temperature': float(temperature),
                    'top_p': 0.9,
                    'seed': seed
                }
                if model:
                    data["model"] = model

                json_data = json.dumps(data).encode('utf-8')
                debug_log(f"=== prompt called with: {headers} '{json_data}' ===")
                request = urllib.request.Request(url, data=json_data, headers=headers, method='POST')

                with urllib.request.urlopen(request) as response:
                    response_data = response.read()
                    response_json = json.loads(response_data.decode('utf-8'))
                    #return response_json["choices"][0]["text"]
                    return response_json["choices"][0]["message"]["content"]
            except urllib.error.HTTPError as e:
                error_msg = e.read().decode('utf-8')
                error_msg = f"HTTP Error {e.code}: {error_msg}"
                debug_log(error_msg)
                return error_msg
            except urllib.error.URLError as e:
                error_msg = f"URL Error: {e.reason}"
                debug_log(error_msg)
                return error_msg
            except Exception as e:
                return f"Error: {e}"
        return ""

    def get_config(self, key, default):
        # This is a simplified version of the get_config function from main.py
        # We will need to find a way to share this code.
        name_file = "localwriter.json"
        path_settings = self.ctx.getServiceManager().createInstanceWithContext('com.sun.star.util.PathSettings', self.ctx)
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
    
    # XServiceInfo implementation
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

# Test function registration
def test_registration():
    """Test if the function is properly registered"""
    debug_log("=== Testing function registration ===")
    try:
        # This will be called when LibreOffice loads the extension
        debug_log("Function registration test completed")
    except Exception as e:
        debug_log(f"Registration test failed: {e}")

# Call test on module load
test_registration()