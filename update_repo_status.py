#!/usr/bin/env python3
"""
Repository Status Updater
Updates the repository status dashboard in README.md with live GitHub data
"""

import os
import re
import requests
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

class GitHubRepoUpdater:
    def __init__(self, username: str, token: str):
        self.username = username
        self.token = token
        self.headers = {
            'Authorization': f'token {token}',
            'Accept': 'application/vnd.github.v3+json'
        }
        self.api_base = 'https://api.github.com'
    
    def get_repo_info(self, repo_name: str) -> Optional[Dict]:
        """Fetch repository information from GitHub API"""
        url = f'{self.api_base}/repos/{self.username}/{repo_name}'
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            print(f"Error fetching repo {repo_name}: {e}")
            return None
    
    def get_repo_commits(self, repo_name: str, days: int = 30) -> List[Dict]:
        """Get recent commits for a repository"""
        since_date = (datetime.now() - timedelta(days=days)).isoformat()
        url = f'{self.api_base}/repos/{self.username}/{repo_name}/commits'
        params = {'since': since_date, 'per_page': 100}
        
        try:
            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            print(f"Error fetching commits for {repo_name}: {e}")
            return []
    
    def get_repo_languages(self, repo_name: str) -> Dict[str, int]:
        """Get programming languages used in repository"""
        url = f'{self.api_base}/repos/{self.username}/{repo_name}/languages'
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            print(f"Error fetching languages for {repo_name}: {e}")
            return {}
    
    def get_primary_language(self, languages: Dict[str, int]) -> str:
        """Determine primary language from language statistics"""
        if not languages:
            return "Unknown"
        return max(languages.items(), key=lambda x: x[1])[0]
    
    def get_repo_status(self, repo_name: str) -> str:
        """Determine repository status based on recent activity"""
        commits = self.get_repo_commits(repo_name, days=90)
        
        if not commits:
            return "Inactive"
        
        recent_commits = len([c for c in commits if 
                            datetime.fromisoformat(c['commit']['author']['date'].replace('Z', '+00:00')) 
                            > datetime.now().replace(tzinfo=None) - timedelta(days=30)])
        
        if recent_commits >= 10:
            return "Very Active"
        elif recent_commits >= 5:
            return "Active"
        elif recent_commits >= 1:
            return "Maintained"
        else:
            return "Inactive"
    
    def format_number(self, num: int) -> str:
        """Format numbers for display (e.g., 1000 -> 1k)"""
        if num >= 1000000:
            return f"{num/1000000:.1f}M"
        elif num >= 1000:
            return f"{num/1000:.1f}k"
        else:
            return str(num)
    
    def format_date(self, date_string: str) -> str:
        """Format ISO date string to readable format"""
        if not date_string:
            return "Never"
        try:
            date_obj = datetime.fromisoformat(date_string.replace('Z', '+00:00'))
            now = datetime.now(date_obj.tzinfo)
            diff = now - date_obj
            
            if diff.days == 0:
                return "Today"
            elif diff.days == 1:
                return "Yesterday"
            elif diff.days < 7:
                return f"{diff.days} days ago"
            elif diff.days < 30:
                return f"{diff.days // 7} weeks ago"
            elif diff.days < 365:
                return f"{diff.days // 30} months ago"
            else:
                return date_obj.strftime('%Y-%m-%d')
        except:
            return "Unknown"
    
    def get_language_badge(self, language: str) -> str:
        """Get language badge markdown"""
        language_badges = {
            'Python': '![Python](https://img.shields.io/badge/Python-3776AB?style=flat&logo=python&logoColor=white)',
            'JavaScript': '![JavaScript](https://img.shields.io/badge/JavaScript-F7DF1E?style=flat&logo=javascript&logoColor=black)',
            'TypeScript': '![TypeScript](https://img.shields.io/badge/TypeScript-007ACC?style=flat&logo=typescript&logoColor=white)',
            'React': '![React](https://img.shields.io/badge/React-20232A?style=flat&logo=react&logoColor=61DAFB)',
            'Next.js': '![Next.js](https://img.shields.io/badge/Next.js-000000?style=flat&logo=next.js&logoColor=white)',
            'Vue.js': '![Vue.js](https://img.shields.io/badge/Vue.js-35495E?style=flat&logo=vue.js&logoColor=4FC08D)',
            'Angular': '![Angular](https://img.shields.io/badge/Angular-DD0031?style=flat&logo=angular&logoColor=white)',
            'Node.js': '![Node.js](https://img.shields.io/badge/Node.js-43853D?style=flat&logo=node.js&logoColor=white)',
            'Java': '![Java](https://img.shields.io/badge/Java-ED8B00?style=flat&logo=java&logoColor=white)',
            'C++': '![C++](https://img.shields.io/badge/C++-00599C?style=flat&logo=c%2B%2B&logoColor=white)',
            'Go': '![Go](https://img.shields.io/badge/Go-00ADD8?style=flat&logo=go&logoColor=white)',
            'Rust': '![Rust](https://img.shields.io/badge/Rust-000000?style=flat&logo=rust&logoColor=white)',
        }
        return language_badges.get(language, f'![{language}](https://img.shields.io/badge/{language}-gray?style=flat)')
    
    def get_status_badge(self, status: str) -> str:
        """Get status badge markdown"""
        status_colors = {
            'Very Active': 'brightgreen',
            'Active': 'green',
            'Maintained': 'yellow',
            'Inactive': 'red'
        }
        color = status_colors.get(status, 'gray')
        return f'![{status}](https://img.shields.io/badge/Status-{status.replace(" ", "%20")}-{color})'
    
    def update_repository_table(self, readme_content: str, repositories: List[str]) -> str:
        """Update the repository status table in README content"""
        
        # Build new table rows
        new_rows = []
        for repo_name in repositories:
            print(f"Processing repository: {repo_name}")
            
            repo_info = self.get_repo_info(repo_name)
            if not repo_info:
                print(f"Skipping {repo_name} - could not fetch info")
                continue
            
            # Get repository statistics
            stars = repo_info.get('stargazers_count', 0)
            forks = repo_info.get('forks_count', 0)
            issues = repo_info.get('open_issues_count', 0)
            last_commit = repo_info.get('updated_at', '')
            
            # Get additional info
            languages = self.get_repo_languages(repo_name)
            primary_language = self.get_primary_language(languages)
            status = self.get_repo_status(repo_name)
            
            # Format badges and data
            status_badge = self.get_status_badge(status)
            language_badge = self.get_language_badge(primary_language)
            stars_badge = f'![Stars](https://img.shields.io/github/stars/{self.username}/{repo_name})'
            forks_badge = f'![Forks](https://img.shields.io/github/forks/{self.username}/{repo_name})'
            issues_badge = f'![Issues](https://img.shields.io/github/issues/{self.username}/{repo_name})'
            last_commit_badge = f'![Last Commit](https://img.shields.io/github/last-commit/{self.username}/{repo_name})'
            
            # Create table row
            row = f"| {repo_name} | {status_badge} | {language_badge} | {stars_badge} | {forks_badge} | {issues_badge} | {last_commit_badge} |"
            new_rows.append(row)
        
        # Find and replace the table in README
        table_pattern = r'(\| Repository \| Status \| Language \| Stars \| Forks \| Issues \| Last Commit \|\n\|.*?\n)((?:\|.*?\n)*)'
        
        if re.search(table_pattern, readme_content):
            # Replace existing table
            new_table = "\n".join(new_rows)
            readme_content = re.sub(
                table_pattern,
                r'\1' + new_table + '\n',
                readme_content,
                flags=re.MULTILINE
            )
        else:
            print("Could not find repository table to update")
        
        return readme_content
    
    def update_activity_stats(self, readme_content: str) -> str:
        """Update activity statistics in README"""
        
        # Get user statistics
        user_url = f'{self.api_base}/users/{self.username}'
        try:
            response = requests.get(user_url, headers=self.headers)
            response.raise_for_status()
            user_data = response.json()
            
            # Update stats if patterns are found
            public_repos = user_data.get('public_repos', 0)
            followers = user_data.get('followers', 0)
            following = user_data.get('following', 0)
            
            print(f"User stats - Repos: {public_repos}, Followers: {followers}, Following: {following}")
            
        except requests.RequestException as e:
            print(f"Error fetching user stats: {e}")
        
        return readme_content

def main():
    """Main function to run the repository status updater"""
    
    # Get environment variables
    github_token = os.environ.get('GITHUB_TOKEN')  # This will be PERSONAL_ACCESS_TOKEN from workflow
    username = os.environ.get('GITHUB_USERNAME', 'thinkdatalabs')
    
    if not github_token:
        print("Error: GITHUB_TOKEN environment variable not set")
        print("Make sure PERSONAL_ACCESS_TOKEN is configured in repository secrets")
        return
    
    # Initialize updater
    updater = GitHubRepoUpdater(username, github_token)
    
    # Define repositories to track
    repositories = [
        'python-data-analytics',
        'ml-model-deployment',
        'react-component-library',
        'nextjs-applications'
    ]
    
    # Read README.md
    readme_path = 'README.md'
    if not os.path.exists(readme_path):
        print(f"Error: {readme_path} not found")
        return
    
    with open(readme_path, 'r', encoding='utf-8') as file:
        readme_content = file.read()
    
    print("Updating repository status table...")
    updated_content = updater.update_repository_table(readme_content, repositories)
    
    print("Updating activity statistics...")
    updated_content = updater.update_activity_stats(updated_content)
    
    # Write updated content back to README
    with open(readme_path, 'w', encoding='utf-8') as file:
        file.write(updated_content)
    
    print("✅ Repository status updated successfully!")

if __name__ == "__main__":
    main()
