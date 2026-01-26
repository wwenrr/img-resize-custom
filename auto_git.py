#!/usr/bin/env python3
"""
Auto Git - Automatically commit and push changes every 60 seconds
Usage: python3 auto_git.py
Press Ctrl+C to stop
"""

import subprocess
import time
import sys
from datetime import datetime

def run_command(command):
    """Run a shell command and return output"""
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            cwd='/home/mk/Desktop/img-resize'
        )
        return result.returncode, result.stdout, result.stderr
    except Exception as e:
        return 1, "", str(e)

def git_auto_commit_push():
    """Auto commit and push changes"""
    print(f"\n{'='*60}")
    print(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")
    
    # Check if there are changes
    code, stdout, stderr = run_command("git status --porcelain")
    
    if not stdout.strip():
        print("✓ No changes to commit")
        return True
    
    print(f"📝 Changes detected:\n{stdout}")
    
    # Git add
    print("\n[1/3] Adding files...")
    code, stdout, stderr = run_command("git add .")
    if code != 0:
        print(f"❌ Git add failed: {stderr}")
        return False
    print("✓ Git add successful")
    
    # Git commit
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    commit_msg = f"auto: update {timestamp}"
    
    print("\n[2/3] Committing...")
    code, stdout, stderr = run_command(f'git commit -m "{commit_msg}"')
    if code != 0:
        if "nothing to commit" in stderr or "nothing to commit" in stdout:
            print("✓ Nothing to commit")
            return True
        print(f"❌ Git commit failed: {stderr}")
        return False
    print(f"✓ Committed: {commit_msg}")
    
    # Git push
    print("\n[3/3] Pushing to remote...")
    code, stdout, stderr = run_command("git push origin main")
    if code != 0:
        print(f"❌ Git push failed: {stderr}")
        return False
    print("✓ Pushed successfully")
    
    return True

def main():
    """Main loop"""
    print("=" * 60)
    print("🤖 Auto Git - Starting...")
    print("=" * 60)
    print("📁 Working directory: /home/mk/Desktop/img-resize")
    print("⏱️  Interval: 60 seconds")
    print("🛑 Press Ctrl+C to stop")
    print("=" * 60)
    
    interval = 60  # seconds
    
    try:
        while True:
            try:
                git_auto_commit_push()
            except Exception as e:
                print(f"\n❌ Error: {e}")
            
            # Wait for next interval
            print(f"\n⏸️  Waiting {interval} seconds...")
            time.sleep(interval)
            
    except KeyboardInterrupt:
        print("\n\n" + "=" * 60)
        print("🛑 Stopped by user")
        print("=" * 60)
        sys.exit(0)

if __name__ == "__main__":
    main()
