import os
import requests
import urllib.parse
import json
import base64
from datetime import datetime, timedelta, timezone
from flask import Flask, render_template, request, flash, session

app = Flask(__name__, static_folder='static', template_folder='templates')
app.secret_key = os.environ.get('FLASK_SECRET', 'dev_secret')
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # 5MB max

GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN', '')
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')

def get_github_headers(use_token=True):
    headers = {'Accept': 'application/vnd.github.v3+json'}
    token = GITHUB_TOKEN.strip()
    if use_token and token:
        # Support both classic tokens (ghp_) and fine-grained tokens (github_pat_)
        headers['Authorization'] = f'Bearer {token}'
    return headers

def github_get(url):
    """Try with token first, fall back to unauthenticated if 401."""
    resp = requests.get(url, headers=get_github_headers(use_token=True), timeout=10)
    if resp.status_code == 401:
        # Token invalid or expired — retry without auth (public repos still work)
        resp = requests.get(url, headers=get_github_headers(use_token=False), timeout=10)
    return resp

def analyze_repo_data(username):
    try:
        url = f'https://api.github.com/users/{username}/repos?per_page=100&sort=pushed'
        resp = github_get(url)
        if resp.status_code == 404:
            return None, f'GitHub username "{username}" not found. Please check the spelling.'
        if resp.status_code == 403:
            return None, f'GitHub rate limit reached. Add a GITHUB_TOKEN environment variable to increase limits.'
        if resp.status_code != 200:
            return None, f'GitHub API error {resp.status_code}: {resp.reason}. Ensure the username is correct and public.'
        repos = resp.json()
        if not isinstance(repos, list) or len(repos) == 0:
            return None, 'No repositories found for this GitHub username.'
    except Exception as e:
        return None, f'Error fetching repositories: {str(e)}'

    total_stars = sum(r.get('stargazers_count', 0) for r in repos)
    total_forks = sum(r.get('forks_count', 0) for r in repos)
    total_repos = len(repos)
    languages = {}
    recent_push = 0
    has_readme = 0
    has_tests = 0
    total_commits = 0
    total_prs = 0
    total_issues = 0
    twenty_ninety_days_ago = datetime.now(timezone.utc) - timedelta(days=90)

    for r in repos:
        lang = r.get('language') or 'Unknown'
        languages[lang] = languages.get(lang, 0) + 1
        pushed_at = r.get('pushed_at')
        if pushed_at:
            try:
                pushed_date = datetime.fromisoformat(pushed_at.replace('Z', '+00:00'))
                if pushed_date > twenty_ninety_days_ago:
                    recent_push += 1
            except:
                pass
        try:
            readme_url = f'https://api.github.com/repos/{username}/{r["name"]}/contents/README.md'
            readme_resp = github_get(readme_url)
            if readme_resp.status_code == 200:
                has_readme += 1
        except:
            pass
        try:
            contents_url = f'https://api.github.com/repos/{username}/{r["name"]}/contents'
            contents_resp = github_get(contents_url)
            if contents_resp.status_code == 200:
                contents = contents_resp.json()
                if any(item['name'].lower() in ['test', 'tests', 'spec', 'specs'] for item in contents if item['type'] == 'dir'):
                    has_tests += 1
        except:
            pass
        try:
            commits_url = f'https://api.github.com/repos/{username}/{r["name"]}/commits?per_page=30'
            commits_resp = github_get(commits_url)
            if commits_resp.status_code == 200:
                total_commits += len(commits_resp.json())
        except:
            pass
        try:
            prs_url = f'https://api.github.com/repos/{username}/{r["name"]}/pulls?state=all&per_page=30'
            prs_resp = github_get(prs_url)
            if prs_resp.status_code == 200:
                total_prs += len(prs_resp.json())
        except:
            pass
        try:
            issues_url = f'https://api.github.com/repos/{username}/{r["name"]}/issues?state=all&per_page=30'
            issues_resp = github_get(issues_url)
            if issues_resp.status_code == 200:
                total_issues += len(issues_resp.json())
        except:
            pass

    score = int(min(100, (total_stars * 0.3) + (total_forks * 0.2) + (total_repos * 2) + (recent_push * 3) + (has_readme * 5) + (has_tests * 5) + (total_commits * 0.1) + (total_prs * 0.5) + (total_issues * 0.2)))
    score = max(10, score)

    strengths, weaknesses, recommendations = [], [], []
    if total_stars >= 50: strengths.append('Strong star count—your projects attract attention.')
    else:
        weaknesses.append('Low star count; consider better discovery and docs.')
        recommendations.append('Write project README and share on social networks.')
    if total_forks >= 20: strengths.append('High fork engagement indicates useful code.')
    else:
        weaknesses.append('Low fork count; encourage contributions.')
        recommendations.append('Invite collaborators and promote open-source adaptation.')
    if total_repos >= 5: strengths.append('Multiple active repositories show good breadth.')
    else:
        weaknesses.append('Few repositories; add more projects for diversity.')
        recommendations.append('Add 2-3 new focused repos (web app, data pipeline, API).')
    if recent_push >= max(1, total_repos // 2): strengths.append('Recent activity across repos demonstrates consistency.')
    else:
        weaknesses.append('Project activity is stale. Push frequent updates.')
        recommendations.append('Commit and push code weekly at minimum.')
    if len(languages) >= 2: strengths.append('Multi-language skill is visible in your portfolio.')
    else:
        weaknesses.append('Limited language diversity; try secondary language projects.')
        recommendations.append('Add projects in another language (e.g., JS, SQL, Go).')
    if has_readme >= max(1, total_repos // 2): strengths.append('Good documentation with README files.')
    else:
        weaknesses.append('Missing README files in many repos.')
        recommendations.append('Add detailed README.md to each project.')
    if has_tests >= max(1, total_repos // 3): strengths.append('Test coverage indicates quality code.')
    else:
        weaknesses.append('Limited test coverage.')
        recommendations.append('Add unit tests and integration tests.')
    if total_prs > 0: strengths.append('Active collaboration with pull requests.')
    else:
        weaknesses.append('No pull requests; consider contributing to others.')
        recommendations.append('Open PRs on popular repos or invite contributions.')

    if 'Unknown' in languages:
        languages.pop('Unknown')

    jobs = ['Junior Python Developer', 'Junior Full-Stack Developer']
    if total_repos >= 8 and has_tests >= 3: jobs.append('Mid-level Developer (with stronger portfolio)')
    if total_stars >= 100: jobs.append('Senior Developer (high visibility)')

    skills = set()
    if 'Python' in languages: skills.add('Python development')
    if 'JavaScript' in languages: skills.add('JavaScript / web development')
    if 'SQL' in languages: skills.add('Database design / SQL')
    if 'HTML' in languages or 'CSS' in languages: skills.add('Frontend design (HTML/CSS)')
    if has_tests >= 1: skills.add('Test-driven development (TDD)')
    if recent_push >= max(1, total_repos // 2): skills.add('Continuous activity and iteration')
    if total_prs >= 3: skills.add('Collaborative open-source contributions')
    if not skills: skills.add('Broaden skill set with new projects and tools')

    return {
        'score': score, 'strengths': strengths, 'weaknesses': weaknesses,
        'recommendations': recommendations, 'jobs': jobs, 'skills': sorted(skills),
        'stats': {
            'stars': total_stars, 'forks': total_forks, 'repos': total_repos,
            'languages': languages, 'recent_push': recent_push, 'has_readme': has_readme,
            'has_tests': has_tests, 'total_commits': total_commits,
            'total_prs': total_prs, 'total_issues': total_issues,
        },
    }, None


def analyze_resume_free(pdf_bytes):
    try:
        import io
        try:
            from pypdf import PdfReader
        except ImportError:
            from PyPDF2 import PdfReader
        reader = PdfReader(io.BytesIO(pdf_bytes))
        text = ' '.join(page.extract_text() or '' for page in reader.pages).lower()
        if not text.strip():
            return {'error': 'Could not extract text from PDF. Make sure it is not a scanned image PDF.'}

        skill_keywords = {
            'Python': ['python'], 'Java': ['java'], 'JavaScript': ['javascript', 'js'],
            'C/C++': ['c++', ' c ', 'c programming'], 'SQL': ['sql', 'mysql', 'postgresql', 'sqlite'],
            'HTML/CSS': ['html', 'css'], 'React': ['react'], 'Flask': ['flask'],
            'Django': ['django'], 'Spring Boot': ['spring boot', 'springboot'],
            'Git': ['git', 'github', 'gitlab'], 'Docker': ['docker'],
            'Machine Learning': ['machine learning', 'ml ', 'scikit', 'tensorflow', 'keras', 'pytorch'],
            'Data Analysis': ['pandas', 'numpy', 'matplotlib', 'data analysis'],
            'REST API': ['rest api', 'restful', 'api development'],
            'Linux': ['linux', 'ubuntu', 'bash'], 'AWS': ['aws', 'amazon web services'],
            'MongoDB': ['mongodb', 'mongoose'], 'Node.js': ['node.js', 'nodejs'],
        }
        skills_found = [skill for skill, kws in skill_keywords.items() if any(kw in text for kw in kws)]

        has_education    = any(w in text for w in ['education', 'university', 'college', 'degree', 'b.e', 'b.tech', 'bca', 'mca'])
        has_experience   = any(w in text for w in ['experience', 'internship', 'intern', 'worked at', 'employment'])
        has_projects     = any(w in text for w in ['project', 'built', 'developed', 'created', 'implemented'])
        has_contact      = any(w in text for w in ['email', 'phone', 'linkedin', 'github', 'contact'])
        has_achievements = any(w in text for w in ['achievement', 'award', 'certificate', 'certif', 'hackathon'])
        has_summary      = any(w in text for w in ['summary', 'objective', 'profile', 'about me'])

        ats_score = 30
        ats_score += 10 if has_education else 0
        ats_score += 15 if has_experience else 0
        ats_score += 15 if has_projects else 0
        ats_score += 10 if has_contact else 0
        ats_score += 10 if has_achievements else 0
        ats_score += 5  if has_summary else 0
        ats_score += min(15, len(skills_found) * 2)
        ats_score = min(ats_score, 100)

        strengths = []
        if has_contact:      strengths.append('Contact information is present.')
        if has_projects:     strengths.append('Projects section found - shows practical experience.')
        if has_education:    strengths.append('Education section is included.')
        if has_experience:   strengths.append('Work/internship experience is mentioned.')
        if has_achievements: strengths.append('Achievements or certifications are listed.')
        if len(skills_found) >= 5: strengths.append(f'Strong skill set detected ({len(skills_found)} skills).')
        if not strengths:    strengths.append('Resume uploaded - add more sections for better scoring.')

        weaknesses = []
        if not has_summary:      weaknesses.append('No objective/summary section - add a 2-3 line profile summary.')
        if not has_experience:   weaknesses.append('No internship/work experience found - add projects or freelance work.')
        if not has_achievements: weaknesses.append('No certifications found - add any online courses or awards.')
        if len(skills_found) < 4: weaknesses.append('Few technical skills detected - list all tools and technologies.')
        if not has_projects:     weaknesses.append('No projects section - add at least 2-3 projects with descriptions.')

        recommendations = [
            'Use action verbs like "Developed", "Designed", "Implemented" for each bullet.',
            'Keep resume to 1 page for freshers - remove irrelevant details.',
            'Add GitHub profile link and LinkedIn URL in contact section.',
            'Quantify achievements (e.g., "Reduced load time by 30%") wherever possible.',
            'Use ATS-friendly formatting - avoid tables, images, or fancy fonts.',
        ]

        return {
            'summary': f'Resume analyzed. {len(skills_found)} technical skills detected across {len(reader.pages)} page(s).',
            'strengths': strengths, 'weaknesses': weaknesses,
            'skills_found': skills_found if skills_found else ['No common tech skills detected - add a skills section explicitly.'],
            'ats_score': ats_score, 'recommendations': recommendations,
        }
    except Exception as e:
        return {'error': f'Resume analysis failed: {str(e)}'}


def analyze_linkedin_free(linkedin_url):
    username = ''
    try:
        parts = [p for p in linkedin_url.rstrip('/').split('/') if p]
        if 'in' in parts:
            username = parts[parts.index('in') + 1].split('?')[0]
    except Exception:
        pass

    name_hint = f'(@{username})' if username else ''
    return {
        'headline_advice': (
            'Write a headline like "Final Year CS Student | Python & Flask Developer | Open to Internships" '
            '- include your role, top skills, and what you are seeking.'
        ),
        'profile_tips': [
            f'Add a professional photo {name_hint} - profiles with photos get 14x more views.',
            'Write a 3-5 line "About" section highlighting your skills, projects, and career goal.',
            'List all projects with a short description, tech stack used, and a GitHub link.',
            'Add education details with your degree, college name, and graduation year.',
            'Request 2-3 LinkedIn recommendations from professors or project teammates.',
        ],
        'visibility_tips': [
            'Turn on "Open to Work" so recruiters can find you easily.',
            'Add relevant skills (Python, Flask, MySQL, etc.) and get endorsements from connections.',
            'Post about your projects or learning journey - even 1 post/week boosts visibility.',
        ],
        'networking_tips': [
            'Connect with 5-10 professionals in your target field every week with a short note.',
            'Follow and engage with companies you want to work at - comment on their posts.',
        ],
    }


def analyze_portfolio_url(portfolio_url):
    """Rule-based portfolio website analysis."""
    try:
        if not portfolio_url.startswith('http'):
            portfolio_url = 'https://' + portfolio_url

        try:
            resp = requests.get(portfolio_url, timeout=10, headers={'User-Agent': 'PortIQ-Bot/1.0'})
        except Exception as e:
            return {'error': f'Could not reach portfolio URL: {str(e)}', 'url': portfolio_url}

        if resp.status_code != 200:
            return {'error': f'Portfolio URL returned status {resp.status_code}. Make sure the site is publicly accessible.', 'url': portfolio_url}

        html = resp.text.lower()

        # Section detection
        section_keywords = {
            'About': ['about', 'who i am', 'about me'],
            'Projects': ['projects', 'my work', 'portfolio', 'showcase'],
            'Skills': ['skills', 'technologies', 'tech stack', 'tools'],
            'Contact': ['contact', 'get in touch', 'reach me', 'email'],
            'Resume/CV': ['resume', 'cv', 'download', 'curriculum'],
            'Blog': ['blog', 'articles', 'posts', 'writing'],
            'Experience': ['experience', 'work history', 'career', 'internship'],
            'Education': ['education', 'university', 'college', 'degree'],
        }

        sections_found = [sec for sec, kws in section_keywords.items() if any(kw in html for kw in kws)]

        # Social links
        has_github   = 'github.com' in html
        has_linkedin = 'linkedin.com' in html
        has_twitter  = 'twitter.com' in html or 'x.com' in html

        # Tech quality signals
        has_meta_desc = '<meta name="description"' in resp.text.lower()
        has_og_tags   = 'og:title' in resp.text.lower() or 'property="og:' in resp.text.lower()
        has_https     = portfolio_url.startswith('https')
        page_size_kb  = len(resp.content) / 1024
        is_fast       = page_size_kb < 500  # simple proxy for page weight

        # Score
        score = 30
        score += len(sections_found) * 7
        score += 10 if has_github else 0
        score += 8  if has_linkedin else 0
        score += 5  if has_meta_desc else 0
        score += 5  if has_og_tags else 0
        score += 5  if has_https else 0
        score += 5  if is_fast else 0
        score = min(100, score)

        strengths, weaknesses, recommendations = [], [], []

        if 'Projects' in sections_found:
            strengths.append('Projects section found — great for showcasing your work.')
        else:
            weaknesses.append('No projects section detected — add 3-5 projects with descriptions.')
            recommendations.append('Create a dedicated "Projects" section with tech stack, live link & GitHub link.')

        if 'Contact' in sections_found:
            strengths.append('Contact section present — makes it easy for recruiters to reach you.')
        else:
            weaknesses.append('No contact section found.')
            recommendations.append('Add a contact form or email address so recruiters can easily reach you.')

        if 'About' in sections_found:
            strengths.append('About/bio section present — helps visitors understand who you are.')
        else:
            weaknesses.append('No about/bio section found.')
            recommendations.append('Add an "About Me" section with your background, skills, and career goal.')

        if 'Skills' in sections_found:
            strengths.append('Skills section detected — highlights your technical competencies.')
        else:
            weaknesses.append('No skills section found — recruiters want to scan your tech stack fast.')
            recommendations.append('Add a skills/tech stack section with icons or pill badges.')

        if has_github:
            strengths.append('GitHub profile is linked — great for recruiters to explore your code.')
        else:
            weaknesses.append('No GitHub link found on your portfolio.')
            recommendations.append('Add your GitHub profile link prominently on the portfolio.')

        if has_linkedin:
            strengths.append('LinkedIn profile is linked.')
        else:
            recommendations.append('Add your LinkedIn profile URL to the portfolio.')

        if has_meta_desc:
            strengths.append('Meta description is set — good for search engine visibility (SEO).')
        else:
            weaknesses.append('Missing meta description — hurts SEO and search discoverability.')
            recommendations.append('Add <meta name="description"> with a short bio + key skills.')

        if has_https:
            strengths.append('Site is served over HTTPS — secure and trusted by browsers.')
        else:
            weaknesses.append('Site is not on HTTPS — switch to HTTPS for security and SEO.')

        if 'Resume/CV' in sections_found:
            strengths.append('Resume/CV download link found — very helpful for recruiters.')
        else:
            recommendations.append('Add a downloadable resume link so recruiters can save your profile.')

        if not is_fast:
            weaknesses.append('Portfolio page is large (>500KB) — may load slowly on mobile.')
            recommendations.append('Optimize images and minify CSS/JS to improve page load speed.')

        return {
            'url': portfolio_url,
            'score': score,
            'sections_found': sections_found,
            'strengths': strengths,
            'weaknesses': weaknesses,
            'recommendations': recommendations,
            'has_github': has_github,
            'has_linkedin': has_linkedin,
            'has_https': has_https,
        }

    except Exception as e:
        return {'error': f'Portfolio analysis failed: {str(e)}', 'url': portfolio_url}


def parse_github_inputs(github_inputs):
    owners = []
    for line in github_inputs.splitlines():
        raw = line.strip()
        if not raw:
            continue
        if 'github.com' in raw:
            try:
                u = urllib.parse.urlparse(raw if raw.startswith('http') else 'https://' + raw)
                parts = [p for p in u.path.split('/') if p]
                if parts:
                    owners.append(parts[0])
            except Exception:
                continue
        else:
            owners.append(raw)
    seen = set()
    deduped = []
    for o in owners:
        if o not in seen:
            seen.add(o)
            deduped.append(o)
    return deduped


def aggregate_analysis_results(analyses):
    if not analyses:
        return None
    aggregate = {
        'score': int(min(100, max(10, round(sum(a['score'] for a in analyses) / len(analyses))))),
        'strengths': [], 'weaknesses': [], 'recommendations': [],
        'jobs': [], 'skills': [],
        'stats': {'stars': 0, 'forks': 0, 'repos': 0, 'languages': {},
                  'recent_push': 0, 'has_readme': 0, 'has_tests': 0,
                  'total_commits': 0, 'total_prs': 0, 'total_issues': 0},
    }
    for a in analyses:
        aggregate['strengths'].extend(a.get('strengths', []))
        aggregate['weaknesses'].extend(a.get('weaknesses', []))
        aggregate['recommendations'].extend(a.get('recommendations', []))
        aggregate['jobs'].extend(a.get('jobs', []))
        aggregate['skills'].extend(a.get('skills', []))
        stats = a.get('stats', {})
        for k in ['stars', 'forks', 'repos', 'recent_push', 'has_readme', 'has_tests', 'total_commits', 'total_prs', 'total_issues']:
            aggregate['stats'][k] += stats.get(k, 0)
        for lang, count in stats.get('languages', {}).items():
            aggregate['stats']['languages'][lang] = aggregate['stats']['languages'].get(lang, 0) + count

    for key in ['strengths', 'weaknesses', 'recommendations', 'jobs', 'skills']:
        aggregate[key] = list(dict.fromkeys(aggregate[key]))
    return aggregate


@app.route('/')
def home():
    last_analysis = session.get('last_analysis')
    last_score = last_analysis.get('score') if last_analysis else None
    last_owner = session.get('last_username')
    return render_template('index.html', last_score=last_score, last_owner=last_owner)


@app.route('/evaluate', methods=['GET', 'POST'])
def evaluate():
    if request.method == 'POST':
        github_inputs  = request.form.get('githubInputs', '').strip()
        linkedin       = request.form.get('linkedin', '').strip()
        portfolio_url  = request.form.get('portfolio_url', '').strip()
        resume_file    = request.files.get('resume_file')
        has_resume     = resume_file and resume_file.filename and resume_file.filename.lower().endswith('.pdf')

        if not github_inputs and not linkedin and not has_resume and not portfolio_url:
            flash('Please provide at least one input: GitHub, LinkedIn, Resume PDF, or Portfolio URL.', 'danger')
            return render_template('evaluate.html')

        # GitHub
        analysis = None
        owners = []
        if github_inputs:
            owners = parse_github_inputs(github_inputs)
            if owners:
                analyses = []
                for owner in owners:
                    result, error = analyze_repo_data(owner)
                    if error:
                        flash(f'GitHub error for {owner}: {error}', 'danger')
                        continue
                    analyses.append(result)
                if analyses:
                    analysis = aggregate_analysis_results(analyses)

        # Resume
        resume_analysis = None
        if has_resume:
            resume_analysis = analyze_resume_free(resume_file.read())
        elif resume_file and resume_file.filename:
            flash('Resume must be a PDF file (.pdf).', 'warning')

        # LinkedIn
        linkedin_analysis = None
        if linkedin:
            linkedin_analysis = analyze_linkedin_free(linkedin)

        # Portfolio
        portfolio_analysis = None
        if portfolio_url:
            portfolio_analysis = analyze_portfolio_url(portfolio_url)

        if analysis is None and resume_analysis is None and linkedin_analysis is None and portfolio_analysis is None:
            flash('No valid inputs could be evaluated. Please try again.', 'danger')
            return render_template('evaluate.html')

        if analysis is None:
            analysis = {
                'score': None,
                'strengths': [], 'weaknesses': [], 'recommendations': [],
                'jobs': [], 'skills': [],
                'stats': {'stars': 0, 'forks': 0, 'repos': 0, 'languages': {},
                          'recent_push': 0, 'has_readme': 0, 'has_tests': 0,
                          'total_commits': 0, 'total_prs': 0, 'total_issues': 0}
            }

        session['last_analysis']           = analysis
        session['last_username']           = ', '.join(owners) if owners else (linkedin or portfolio_url or 'User')
        session['last_resume_analysis']    = resume_analysis
        session['last_linkedin_analysis']  = linkedin_analysis
        session['last_portfolio_analysis'] = portfolio_analysis

        return render_template('results.html',
                               username=session['last_username'],
                               linkedin=linkedin,
                               score=analysis.get('score'),
                               strengths=analysis.get('strengths', []),
                               weaknesses=analysis.get('weaknesses', []),
                               recommendations=analysis.get('recommendations', []),
                               jobs=analysis.get('jobs', []),
                               skills=analysis.get('skills', []),
                               stats=analysis.get('stats', {}),
                               resume_analysis=resume_analysis,
                               linkedin_analysis=linkedin_analysis,
                               portfolio_analysis=portfolio_analysis)

    return render_template('evaluate.html')


@app.route('/dashboard')
def dashboard():
    analysis          = session.get('last_analysis')
    username          = session.get('last_username')
    resume_analysis   = session.get('last_resume_analysis')
    linkedin_analysis = session.get('last_linkedin_analysis')
    portfolio_analysis = session.get('last_portfolio_analysis')
    if not analysis and not resume_analysis and not linkedin_analysis and not portfolio_analysis:
        flash('No evaluation data found. Please run an evaluation first.', 'warning')
    return render_template('dashboard.html',
                           analysis=analysis, username=username,
                           resume_analysis=resume_analysis,
                           linkedin_analysis=linkedin_analysis,
                           portfolio_analysis=portfolio_analysis)


@app.route('/about')
def about():
    return render_template('about.html')


@app.route('/results')
def results():
    analysis          = session.get('last_analysis')
    username          = session.get('last_username')
    resume_analysis   = session.get('last_resume_analysis')
    linkedin_analysis = session.get('last_linkedin_analysis')
    portfolio_analysis = session.get('last_portfolio_analysis')

    if not analysis:
        flash('No evaluation data found. Please run an evaluation first.', 'warning')
        return render_template('results.html', username=None, score=None, strengths=[], weaknesses=[],
                               recommendations=[], jobs=[], skills=[], stats={},
                               resume_analysis=None, linkedin_analysis=None, portfolio_analysis=None)
    stats = analysis['stats']
    return render_template('results.html',
                           username=username, score=analysis.get('score'),
                           strengths=analysis.get('strengths', []),
                           weaknesses=analysis.get('weaknesses', []),
                           recommendations=analysis.get('recommendations', []),
                           jobs=analysis.get('jobs', []),
                           skills=analysis.get('skills', []),
                           stats=stats,
                           resume_analysis=resume_analysis,
                           linkedin_analysis=linkedin_analysis,
                           portfolio_analysis=portfolio_analysis)


if __name__ == '__main__':
    app.run(debug=True)
