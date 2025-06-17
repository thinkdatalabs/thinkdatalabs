#!/usr/bin/env python3
"""
Enhanced Repository Status Updater
Updates the repository status dashboard in README.md with live GitHub data
Includes comprehensive error handling, logging, and flexible configuration
"""

import os
import re
import requests
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('repo_updater.log')
    ]
)
logger = logging.getLogger(__name__)

class RepoStatus(Enum):
    """Repository status levels"""
    VERY_ACTIVE = "Very Active"
    ACTIVE = "Active"
    MAINTAINED = "Maintained"
    INACTIVE = "Inactive"
    ARCHIVED = "Archived"

@dataclass
class RepoConfig:
    """Configuration for repository tracking"""
    name: str
    display_name: Optional[str] = None
    track_issues: bool = True
    track_prs: bool = True
    custom_status: Optional[str] = None

class GitHubRepoUpdater:
    """Enhanced GitHub repository status updater"""
    
    def __init__(self, username: str, token: str):
        self.username = username
        self.token = token
        self.headers = {
            'Authorization': f'token {token}',
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': f'GitHub-Updater/{username}'
        }
        self.api_base = 'https://api.github.com'
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        
        # Rate limiting
        self.rate_limit_remaining = None
        self.rate_limit_reset = None
        
        logger.info(f"Initialized GitHubRepoUpdater for user: {username}")
    
    def _check_rate_limit(self) -> bool:
        """Check GitHub API rate limit"""
        try:
            response = self.session.get(f'{self.api_base}/rate_limit')
            response.raise_for_status()
            data = response.json()
            
            core_limit = data['resources']['core']
            self.rate_limit_remaining = core_limit['remaining']
            self.rate_limit_reset = datetime.fromtimestamp(core_limit['reset'])
            
            logger.info(f"Rate limit: {self.rate_limit_remaining} requests remaining")
            
            if self.rate_limit_remaining < 10:
                logger.warning(f"Low rate limit: {self.rate_limit_remaining} requests remaining")
                return False
            return True
            
        except Exception as e:
            logger.error(f"Error checking rate limit: {e}")
            return True  # Continue if rate limit check fails
    
    def _make_request(self, url: str, params: Optional[Dict] = None) -> Optional[Dict]:
        """Make authenticated request to GitHub API with error handling"""
        try:
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.Timeout:
            logger.error(f"Timeout error for URL: {url}")
            return None
        except requests.exceptions.HTTPError as e:
            if response.status_code == 404:
                logger.warning(f"Resource not found: {url}")
            elif response.status_code == 403:
                logger.error(f"Rate limit or permission error: {url}")
            else:
                logger.error(f"HTTP error {response.status_code} for URL: {url}")
            return None
        except requests.RequestException as e:
            logger.error(f"Request error for URL {url}: {e}")
            return None
    
    def get_repo_info(self, repo_name: str) -> Optional[Dict]:
        """Fetch comprehensive repository information"""
        if not self._check_rate_limit():
            return None
            
        url = f'{self.api_base}/repos/{self.username}/{repo_name}'
        data = self._make_request(url)
        
        if data:
            logger.info(f"Successfully fetched info for {repo_name}")
        else:
            logger.warning(f"Failed to fetch info for {repo_name}")
            
        return data
    
    def get_repo_commits(self, repo_name: str, days: int = 30) -> List[Dict]:
        """Get recent commits with pagination support"""
        since_date = (datetime.now() - timedelta(days=days)).isoformat()
        url = f'{self.api_base}/repos/{self.username}/{repo_name}/commits'
        params = {
            'since': since_date,
            'per_page': 100,
            'page': 1
        }
        
        all_commits = []
        
        while True:
            data = self._make_request(url, params)
            if not data:
                break
                
            all_commits.extend(data)
            
            # Check if there are more pages
            if len(data) < 100:
                break
            params['page'] += 1
            
            # Safety limit to prevent infinite loops
            if params['page'] > 10:
                break
        
        logger.info(f"Fetched {len(all_commits)} commits for {repo_name}")
        return all_commits
    
    def get_repo_languages(self, repo_name: str) -> Dict[str, int]:
        """Get programming languages used in repository"""
        url = f'{self.api_base}/repos/{self.username}/{repo_name}/languages'
        data = self._make_request(url)
        return data or {}
    
    def get_repo_pulls(self, repo_name: str, state: str = 'open') -> List[Dict]:
        """Get pull requests for repository"""
        url = f'{self.api_base}/repos/{self.username}/{repo_name}/pulls'
        params = {'state': state, 'per_page': 100}
        data = self._make_request(url, params)
        return data or []
    
    def get_repo_issues(self, repo_name: str, state: str = 'open') -> List[Dict]:
        """Get issues for repository (excluding pull requests)"""
        url = f'{self.api_base}/repos/{self.username}/{repo_name}/issues'
        params = {'state': state, 'per_page': 100}
        data = self._make_request(url, params)
        
        # Filter out pull requests (issues API includes PRs)
        if data:
            return [issue for issue in data if 'pull_request' not in issue]
        return []
    
    def get_primary_language(self, languages: Dict[str, int]) -> str:
        """Determine primary language from language statistics"""
        if not languages:
            return "Unknown"
        return max(languages.items(), key=lambda x: x[1])[0]
    
    def calculate_repo_status(self, repo_info: Dict, commits: List[Dict]) -> RepoStatus:
        """Calculate repository status based on multiple factors"""
        if repo_info.get('archived', False):
            return RepoStatus.ARCHIVED
        
        if not commits:
            return RepoStatus.INACTIVE
        
        # Analyze commit frequency
        now = datetime.now()
        recent_commits_30d = len([
            c for c in commits 
            if self._parse_github_date(c['commit']['author']['date']) > now - timedelta(days=30)
        ])
        recent_commits_7d = len([
            c for c in commits 
            if self._parse_github_date(c['commit']['author']['date']) > now - timedelta(days=7)
        ])
        
        # Determine status based on activity
        if recent_commits_7d >= 5 or recent_commits_30d >= 20:
            return RepoStatus.VERY_ACTIVE
        elif recent_commits_30d >= 5:
            return RepoStatus.ACTIVE
        elif recent_commits_30d >= 1:
            return RepoStatus.MAINTAINED
        else:
            return RepoStatus.INACTIVE
    
    def _parse_github_date(self, date_string: str) -> datetime:
        """Parse GitHub date string to datetime object"""
        try:
            return datetime.fromisoformat(date_string.replace('Z', '+00:00')).replace(tzinfo=None)
        except:
            return datetime.min
    
    def format_number(self, num: int) -> str:
        """Format numbers for display"""
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
            date_obj = self._parse_github_date(date_string)
            now = datetime.now()
            diff = now - date_obj
            
            if diff.days == 0:
                return "Today"
            elif diff.days == 1:
                return "Yesterday"
            elif diff.days < 7:
                return f"{diff.days} days ago"
            elif diff.days < 30:
                weeks = diff.days // 7
                return f"{weeks} week{'s' if weeks > 1 else ''} ago"
            elif diff.days < 365:
                months = diff.days // 30
                return f"{months} month{'s' if months > 1 else ''} ago"
            else:
                return date_obj.strftime('%Y-%m-%d')
        except:
            return "Unknown"
    
    def get_language_badge(self, language: str) -> str:
        """Get language badge markdown with comprehensive language support"""
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
            'C#': '![C#](https://img.shields.io/badge/C%23-239120?style=flat&logo=c-sharp&logoColor=white)',
            'Go': '![Go](https://img.shields.io/badge/Go-00ADD8?style=flat&logo=go&logoColor=white)',
            'Rust': '![Rust](https://img.shields.io/badge/Rust-000000?style=flat&logo=rust&logoColor=white)',
            'PHP': '![PHP](https://img.shields.io/badge/PHP-777BB4?style=flat&logo=php&logoColor=white)',
            'Ruby': '![Ruby](https://img.shields.io/badge/Ruby-CC342D?style=flat&logo=ruby&logoColor=white)',
            'Swift': '![Swift](https://img.shields.io/badge/Swift-FA7343?style=flat&logo=swift&logoColor=white)',
            'Kotlin': '![Kotlin](https://img.shields.io/badge/Kotlin-0095D5?style=flat&logo=kotlin&logoColor=white)',
            'Dart': '![Dart](https://img.shields.io/badge/Dart-0175C2?style=flat&logo=dart&logoColor=white)',
            'HTML': '![HTML](https://img.shields.io/badge/HTML-E34F26?style=flat&logo=html5&logoColor=white)',
            'CSS': '![CSS](https://img.shields.io/badge/CSS-1572B6?style=flat&logo=css3&logoColor=white)',
            'Shell': '![Shell](https://img.shields.io/badge/Shell-4EAA25?style=flat&logo=gnu-bash&logoColor=white)',
            'Dockerfile': '![Docker](https://img.shields.io/badge/Docker-2496ED?style=flat&logo=docker&logoColor=white)',
        }
        return language_badges.get(language, f'![{language}](https://img.shields.io/badge/{language.replace(" ", "%20")}-gray?style=flat)')
    
    def get_status_badge(self, status: RepoStatus) -> str:
        """Get status badge markdown"""
        status_colors = {
            RepoStatus.VERY_ACTIVE: 'brightgreen',
            RepoStatus.ACTIVE: 'green',
            RepoStatus.MAINTAINED: 'yellow',
            RepoStatus.INACTIVE: 'red',
            RepoStatus.ARCHIVED: 'lightgray'
        }
        color = status_colors.get(status, 'gray')
        status_text = status.value.replace(' ', '%20')
        return f'![{status.value}](https://img.shields.io/badge/Status-{status_text}-{color})'
    
    def process_repository(self, repo_config: RepoConfig) -> Optional[str]:
        """Process a single repository and return table row"""
        repo_name = repo_config.name
        display_name = repo_config.display_name or repo_name
        
        logger.info(f"Processing repository: {repo_name}")
        
        # Get repository information
        repo_info = self.get_repo_info(repo_name)
        if not repo_info:
            logger.error(f"Skipping {repo_name} - could not fetch info")
            return None
        
        # Get repository statistics
        commits = self.get_repo_commits(repo_name, days=90)
        languages = self.get_repo_languages(repo_name)
        
        # Calculate metrics
        primary_language = self.get_primary_language(languages)
        status = self.calculate_repo_status(repo_info, commits)
        
        # Use custom status if provided
        if repo_config.custom_status:
            try:
                status = RepoStatus(repo_config.custom_status)
            except ValueError:
                logger.warning(f"Invalid custom status '{repo_config.custom_status}' for {repo_name}")
        
        # Format badges
        status_badge = self.get_status_badge(status)
        language_badge = self.get_language_badge(primary_language)
        stars_badge = f'![Stars](https://img.shields.io/github/stars/{self.username}/{repo_name}?style=flat)'
        forks_badge = f'![Forks](https://img.shields.io/github/forks/{self.username}/{repo_name}?style=flat)'
        
        # Conditional badges
        badges = [status_badge, language_badge, stars_badge, forks_badge]
        
        if repo_config.track_issues:
            issues_badge = f'![Issues](https://img.shields.io/github/issues/{self.username}/{repo_name}?style=flat)'
            badges.append(issues_badge)
        
        last_commit_badge = f'![Last Commit](https://img.shields.io/github/last-commit/{self.username}/{repo_name}?style=flat)'
        badges.append(last_commit_badge)
        
        # Create table row
        row = f"| {display_name} | " + " | ".join(badges) + " |"
        
        logger.info(f"Successfully processed {repo_name}")
        return row
    
    def update_repository_table(self, readme_content: str, repo_configs: List[RepoConfig]) -> str:
        """Update the repository status table in README content"""
        
        # Build new table rows
        new_rows = []
        successful_repos = 0
        
        for repo_config in repo_configs:
            row = self.process_repository(repo_config)
            if row:
                new_rows.append(row)
                successful_repos += 1
        
        if not new_rows:
            logger.error("No repositories were successfully processed")
            return readme_content
        
        # Dynamic table header based on configuration
        headers = ["Repository", "Status", "Language", "Stars", "Forks"]
        if any(config.track_issues for config in repo_configs):
            headers.append("Issues")
        headers.append("Last Commit")
        
        # Find and replace the table in README
        table_pattern = r'(\| Repository \| Status \| Language \| Stars \| Forks \|[^\n]*\n\|[^\n]*\n)((?:\|.*?\n)*)'
        
        if re.search(table_pattern, readme_content, re.MULTILINE):
            # Build new table
            header_row = "| " + " | ".join(headers) + " |"
            separator_row = "|" + "|".join([" --- " for _ in headers]) + "|"
            new_table = header_row + "\n" + separator_row + "\n" + "\n".join(new_rows)
            
            # Replace existing table
            readme_content = re.sub(
                table_pattern,
                new_table + '\n\n',
                readme_content,
                flags=re.MULTILINE
            )
            
            logger.info(f"Successfully updated table with {successful_repos} repositories")
        else:
            logger.warning("Could not find repository table to update")
        
        return readme_content
    
    def update_activity_stats(self, readme_content: str) -> str:
        """Update activity statistics in README"""
        
        try:
            user_url = f'{self.api_base}/users/{self.username}'
            user_data = self._make_request(user_url)
            
            if user_data:
                public_repos = user_data.get('public_repos', 0)
                followers = user_data.get('followers', 0)
                following = user_data.get('following', 0)
                
                logger.info(f"User stats - Repos: {public_repos}, Followers: {followers}, Following: {following}")
                
                # Update last updated timestamp
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
                timestamp_pattern = r'(<!-- LAST_UPDATED:)(.*?)(-->)'
                
                if re.search(timestamp_pattern, readme_content):
                    readme_content = re.sub(
                        timestamp_pattern,
                        f'\\1{timestamp}\\3',
                        readme_content
                    )
                else:
                    # Add timestamp if not present
                    readme_content += f"\n\n<!-- LAST_UPDATED:{timestamp} -->\n"
            
        except Exception as e:
            logger.error(f"Error updating activity stats: {e}")
        
        return readme_content
    
    def generate_summary_report(self, repo_configs: List[RepoConfig]) -> str:
        """Generate a summary report of the update process"""
        report = f"""
=== Repository Update Summary ===
Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
User: {self.username}
Repositories Processed: {len(repo_configs)}
Rate Limit Remaining: {self.rate_limit_remaining}
"""
        
        for config in repo_configs:
            repo_info = self.get_repo_info(config.name)
            if repo_info:
                report += f"\n✅ {config.name} - Last updated: {repo_info.get('updated_at', 'Unknown')}"
            else:
                report += f"\n❌ {config.name} - Failed to fetch"
        
        return report

def load_config() -> Tuple[str, str, List[RepoConfig]]:
    """Load configuration from environment variables and return settings"""
    
    # Get environment variables
    github_token = os.environ.get('GITHUB_TOKEN') or os.environ.get('PERSONAL_ACCESS_TOKEN')
    username = os.environ.get('GITHUB_USERNAME', 'thinkdatalabs')
    
    if not github_token:
        raise ValueError("GITHUB_TOKEN or PERSONAL_ACCESS_TOKEN environment variable not set")
    
    # Repository configurations
    repo_configs = [
        RepoConfig(
            name='python-data-analytics',
            display_name='Python Data Analytics',
            track_issues=True,
            track_prs=True
        ),
        RepoConfig(
            name='ml-model-deployment',
            display_name='ML Model Deployment',
            track_issues=True,
            track_prs=True
        ),
        RepoConfig(
            name='react-component-library',
            display_name='React Component Library',
            track_issues=True,
            track_prs=True
        ),
        RepoConfig(
            name='nextjs-applications',
            display_name='Next.js Applications',
            track_issues=True,
            track_prs=True
        ),
        RepoConfig(
            name='python-api-services',
            display_name='Python API Services',
            track_issues=True,
            track_prs=False
        ),
        RepoConfig(
            name='data-processing-pipelines',
            display_name='Data Processing Pipelines',
            track_issues=True,
            track_prs=True
        )
    ]
    
    return github_token, username, repo_configs

def main():
    """Main function to run the repository status updater"""
    
    try:
        # Load configuration
        github_token, username, repo_configs = load_config()
        
        # Initialize updater
        updater = GitHubRepoUpdater(username, github_token)
        
        # Check README.md exists
        readme_path = 'README.md'
        if not os.path.exists(readme_path):
            logger.error(f"Error: {readme_path} not found")
            return 1
        
        # Read README.md
        with open(readme_path, 'r', encoding='utf-8') as file:
            readme_content = file.read()
        
        logger.info("Starting repository status update...")
        
        # Update repository status table
        logger.info("Updating repository status table...")
        updated_content = updater.update_repository_table(readme_content, repo_configs)
        
        # Update activity statistics
        logger.info("Updating activity statistics...")
        updated_content = updater.update_activity_stats(updated_content)
        
        # Write updated content back to README
        with open(readme_path, 'w', encoding='utf-8') as file:
            file.write(updated_content)
        
        # Generate summary report
        summary = updater.generate_summary_report(repo_configs)
        logger.info(summary)
        
        # Save summary to file
        with open('update_summary.txt', 'w') as f:
            f.write(summary)
        
        logger.info("✅ Repository status updated successfully!")
        return 0
        
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        return 1

if __name__ == "__main__":
    exit(main())
