import os

class PromptLoader:
    """Load and format prompts from text files"""
    
    def __init__(self, prompts_dir="prompts"):
        self.prompts_dir = prompts_dir
        self._cache = {}
    
    def load(self, prompt_name):
        """Load a prompt from file"""
        if prompt_name in self._cache:
            return self._cache[prompt_name]
        
        file_path = os.path.join(self.prompts_dir, f"{prompt_name}.txt")
        
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                prompt_text = f.read()
            self._cache[prompt_name] = prompt_text
            return prompt_text
        except FileNotFoundError:
            raise FileNotFoundError(f"Prompt file not found: {file_path}")
    
    def format(self, prompt_name, **kwargs):
        """Load and format a prompt with variables"""
        prompt_text = self.load(prompt_name)
        return prompt_text.format(**kwargs)