# setup_groq.ps1 - Quick Groq setup

Write-Host "🚀 Setting up Groq for Automaton Auditor..." -ForegroundColor Cyan

# 1. Check if langchain-groq is installed
if (-not (pip show langchain-groq)) {
    Write-Host "📦 Installing langchain-groq..." -ForegroundColor Yellow
    pip install langchain-groq
}

# 2. Prompt for API key if not set
if (-not $env:GROQ_API_KEY) {
    Write-Host ""
    Write-Host "⚠️  GROQ_API_KEY not found!" -ForegroundColor Yellow
    Write-Host "Get your key from: https://console.groq.com"
    Write-Host ""
    $key = Read-Host "Enter your Groq API key (or press Enter to skip)"
    
    if ($key) {
        # Add to .env
        if (Test-Path .env) {
            # Remove existing GROQ_API_KEY line if present
            $lines = Get-Content .env | Where-Object { $_ -notmatch "^GROQ_API_KEY=" }
            $lines | Set-Content .env
        }
        Add-Content .env "GROQ_API_KEY=$key"
        Add-Content .env "LLM_PROVIDER=groq"
        
        # Set for current session
        $env:GROQ_API_KEY = $key
        $env:LLM_PROVIDER = "groq"
        
        Write-Host "✅ GROQ_API_KEY added to .env" -ForegroundColor Green
    }
    else {
        Write-Host "⏭️  Skipping Groq setup. Tests will skip when key is missing." -ForegroundColor Gray
    }
}

# 3. Register pytest marks
if (-not (Select-String -Path "pyproject.toml" -Pattern "markers = \[" -Quiet)) {
    Write-Host "📝 Adding pytest markers to pyproject.toml..." -ForegroundColor Yellow
    Add-Content pyproject.toml ""
    Add-Content pyproject.toml "[tool.pytest.ini_options]"
    Add-Content pyproject.toml "markers = ["
    Add-Content pyproject.toml '    "slow: marks tests as slow (deselect with ''-m \"not slow\"'')",'
    Add-Content pyproject.toml "]"
}

# 4. Run quick validation
Write-Host ""
Write-Host "🧪 Running quick validation..." -ForegroundColor Cyan
pytest tests/test_groq.py -v -m "not slow" --tb=short

Write-Host ""
Write-Host "✨ Setup complete!" -ForegroundColor Green
Write-Host "To run full tests: pytest tests/test_groq.py -v"
Write-Host "To skip slow tests: pytest tests/test_groq.py -v -m 'not slow'"