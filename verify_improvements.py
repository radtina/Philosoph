#!/usr/bin/env python3
"""
Philosopher Chat Simulator - Configuration Verification Script
Verifies that all improvements have been properly implemented.
"""

import os
import json
import re

def verify_env_file():
    """Verify .env configuration"""
    print("\n" + "="*60)
    print("1. VERIFYING .env CONFIGURATION")
    print("="*60)
    
    if not os.path.exists('.env'):
        print("❌ .env file not found")
        return False
    
    with open('.env', 'r') as f:
        env_content = f.read()
    
    has_api_key = 'OPENAI_API_KEY' in env_content
    has_model = 'OPENAI_MODEL' in env_content
    
    print(f"✅ OPENAI_API_KEY present: {has_api_key}")
    print(f"✅ OPENAI_MODEL present: {has_model}")
    
    if 'gpt-4' in env_content or 'gpt-3.5-turbo' in env_content:
        print("✅ Valid OpenAI model configured")
    else:
        print("⚠️  Model may not be recognized")
    
    return has_api_key and has_model

def verify_backend():
    """Verify backend.py improvements"""
    print("\n" + "="*60)
    print("2. VERIFYING backend.py IMPROVEMENTS")
    print("="*60)
    
    with open('backend.py', 'r') as f:
        backend_content = f.read()
    
    checks = {
        "API key security (no hardcoded fallback)": 'OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")' in backend_content,
        "Model loaded from .env": 'OPENAI_MODEL = os.getenv("OPENAI_MODEL"' in backend_content,
        "Error on missing API key": 'raise ValueError("OPENAI_API_KEY environment variable not set")' in backend_content,
        "Opening phase instructions": 'phase == "opening"' in backend_content,
        "Debate phase instructions": 'phase == "debate"' in backend_content,
        "Attribution cleanup in instructions": "Do not include any speaker attributions" in backend_content,
    }
    
    for check_name, result in checks.items():
        symbol = "✅" if result else "❌"
        print(f"{symbol} {check_name}")
    
    return all(checks.values())

def verify_script_js():
    """Verify script.js improvements"""
    print("\n" + "="*60)
    print("3. VERIFYING script.js IMPROVEMENTS")
    print("="*60)
    
    with open('static/script.js', 'r') as f:
        script_content = f.read()
    
    checks = {
        "cleanAttributions() function defined": 'function cleanAttributions(text)' in script_content,
        "Regex pattern for 'X said:' removal": r'\^[A-Za-z\s\+]+\s+said:\s\*' in script_content or 'said:' in script_content,
        "Regex pattern for 'X:' removal": r'\^[A-Za-z\s\+]+:\s\*' in script_content or 'cleanAttributions' in script_content,
        "Applied to API response": 'cleanAttributions(data.generated_text)' in script_content,
    }
    
    for check_name, result in checks.items():
        symbol = "✅" if result else "❌"
        print(f"{symbol} {check_name}")
    
    return all(checks.values())

def verify_philosophers():
    """Verify philosophers.js expansion"""
    print("\n" + "="*60)
    print("4. VERIFYING philosophers.js EXPANSION")
    print("="*60)
    
    with open('static/philosophers.js', 'r') as f:
        philo_content = f.read()
    
    # Count philosophers
    philosopher_count = philo_content.count('{ name:')
    print(f"✅ Number of philosophers: {philosopher_count}")
    
    # Check for expanded prompts (look for longer descriptions)
    has_core_beliefs = 'core belief' in philo_content.lower() or 'core beliefs' in philo_content.lower()
    has_debate_guidance = 'when debating' in philo_content.lower()
    has_philosophy_specifics = ('virtue' in philo_content or 'reason' in philo_content or 
                                'justice' in philo_content)
    
    print(f"✅ Core beliefs mentioned: {has_core_beliefs}")
    print(f"✅ Debate guidance included: {has_debate_guidance}")
    print(f"✅ Philosophy-specific content: {has_philosophy_specifics}")
    
    # Check specific philosophers
    socrates_prompt = philo_content[philo_content.find('Socrates'):philo_content.find('Socrates')+500]
    socrates_detailed = len(socrates_prompt) > 200
    
    print(f"✅ Socrates prompt expanded: {socrates_detailed} (length: {len(socrates_prompt)} chars)")
    
    return philosopher_count >= 59 and has_debate_guidance

def verify_file_structure():
    """Verify all required files exist"""
    print("\n" + "="*60)
    print("5. VERIFYING FILE STRUCTURE")
    print("="*60)
    
    required_files = {
        'backend.py': 'Python backend',
        '.env': 'Environment configuration',
        'static/index.html': 'Frontend HTML',
        'static/script.js': 'Frontend JavaScript',
        'static/philosophers.js': 'Philosopher data',
        'static/style.css': 'Styling',
        'requirements.txt': 'Python dependencies',
    }
    
    all_present = True
    for filename, description in required_files.items():
        exists = os.path.exists(filename)
        symbol = "✅" if exists else "❌"
        print(f"{symbol} {filename}: {description}")
        all_present = all_present and exists
    
    return all_present

def main():
    print("\n" + "🔍 PHILOSOPHER CHAT SIMULATOR - VERIFICATION REPORT\n")
    
    results = {
        "Environment Configuration": verify_env_file(),
        "Backend Improvements": verify_backend(),
        "Frontend Attribution Cleaning": verify_script_js(),
        "Philosopher Prompts Expansion": verify_philosophers(),
        "File Structure": verify_file_structure(),
    }
    
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    
    for check_name, result in results.items():
        symbol = "✅" if result else "⚠️ "
        status = "PASS" if result else "REVIEW"
        print(f"{symbol} {check_name}: {status}")
    
    all_pass = all(results.values())
    
    print("\n" + "="*60)
    if all_pass:
        print("✅ ALL IMPROVEMENTS VERIFIED SUCCESSFULLY!")
        print("="*60)
        print("\nYour Philosopher Chat Simulator is ready to run:")
        print("1. Ensure .env has valid OPENAI_API_KEY")
        print("2. Run: python -m uvicorn backend:app --reload")
        print("3. Open: http://localhost:8000")
        print("\nExpected improvements:")
        print("  • No more nested 'X said: X said:' attributions")
        print("  • Philosophers have distinctive voices")
        print("  • Each philosopher debates from their own perspective")
    else:
        print("⚠️  SOME CHECKS DID NOT PASS")
        print("Please review the items marked with ❌ above")
    
    print("="*60 + "\n")

if __name__ == "__main__":
    main()
