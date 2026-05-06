pipeline {
  agent any

  options {
    timestamps()
    disableConcurrentBuilds()
    buildDiscarder(logRotator(numToKeepStr: '30', artifactNumToKeepStr: '5'))
  }

  parameters {
    choice(name: 'PROVIDER_SCOPE', choices: ['all', 'smoke', 'mts', 'beeline', 'megafon', 't2', 'rostelecom', 'domru'], description: 'Provider scope to run.')
    string(name: 'SITE', defaultValue: '', description: 'Optional site filter. Leave empty to run all provider sites.')
    choice(name: 'SERVICE_MODE', choices: ['core', 'variants', 'all'], description: 'Service mode to run.')

    booleanParam(name: 'RUN_CHROMIUM', defaultValue: true, description: 'Run desktop chromium profile.')
    booleanParam(name: 'RUN_FIREFOX', defaultValue: false, description: 'Run desktop firefox profile.')
    booleanParam(name: 'RUN_WEBKIT', defaultValue: false, description: 'Run desktop webkit profile.')
    booleanParam(name: 'RUN_MOBILE_CHROMIUM', defaultValue: false, description: 'Run mobile chromium profile.')
    booleanParam(name: 'RUN_MOBILE_WEBKIT', defaultValue: false, description: 'Run mobile webkit profile.')

    choice(name: 'BLOCKING_PROFILE', choices: ['none', 'adblock-mvp'], description: 'Blocking profile.')
    booleanParam(name: 'ALERT_ERRORS', defaultValue: true, description: 'Enable single-site error alerts in pytest runtime.')
    booleanParam(name: 'ALERT_AGGREGATES', defaultValue: true, description: 'Enable aggregate alerts in pytest runtime.')
    booleanParam(name: 'ALERT_SUMMARY', defaultValue: true, description: 'Enable summary alerts in pytest runtime.')
    booleanParam(name: 'ALERT_RECOVERED', defaultValue: true, description: 'Enable recovered alerts in pytest runtime.')
    booleanParam(name: 'USE_TELEGRAM_PROXY', defaultValue: true, description: 'Use Jenkins proxy credentials for Telegram alerts.')
  }

  environment {
    PLAYWRIGHT_BROWSERS_PATH = '/var/lib/jenkins/cache/ms-playwright'
    PIP_CACHE_DIR = '/var/lib/jenkins/cache/pip'
    PIP_DISABLE_PIP_VERSION_CHECK = '1'
    PYTHONUNBUFFERED = '1'
    PYTHON_BIN = '.venv/bin/python'
    PYTHON_BIN_FILE = '.python_bin'
    REQ_HASH_FILE = '.requirements.sha256'
    ALERT_ERRORS_ENABLED = "${params.ALERT_ERRORS}"
    ALERT_AGGREGATES_ENABLED = "${params.ALERT_AGGREGATES}"
    ALERT_SUMMARY_ENABLED = "${params.ALERT_SUMMARY}"
    ALERT_RECOVERED_ENABLED = "${params.ALERT_RECOVERED}"
  }

  stages {
    stage('Checkout') {
      steps {
        checkout scm
      }
    }

    stage('Validate parameters') {
      steps {
        script {
          if (!(params.RUN_CHROMIUM || params.RUN_FIREFOX || params.RUN_WEBKIT || params.RUN_MOBILE_CHROMIUM || params.RUN_MOBILE_WEBKIT)) {
            error('Select at least one browser/profile toggle.')
          }
        }
      }
    }

    stage('Cache diagnostics') {
      steps {
        sh '''
          set -e
          echo "=== Cache diagnostics ==="
          echo "Workspace: $(pwd)"

          if [ -x ".venv/bin/python" ]; then
            echo "[VENV] Reused: .venv exists"
            .venv/bin/python --version || true
          else
            echo "[VENV] Missing: .venv will be created"
          fi

          if [ -f ".requirements.sha256" ]; then
            echo "[REQ_HASH] Found: $(cat .requirements.sha256)"
          else
            echo "[REQ_HASH] Missing: deps install expected"
          fi

          if [ -d "${PIP_CACHE_DIR}" ]; then
            echo "[PIP_CACHE] Found: ${PIP_CACHE_DIR}"
            du -sh "${PIP_CACHE_DIR}" || true
          else
            echo "[PIP_CACHE] Missing: ${PIP_CACHE_DIR}"
          fi

          if [ -d "${PLAYWRIGHT_BROWSERS_PATH}" ]; then
            echo "[PW_CACHE] Found: ${PLAYWRIGHT_BROWSERS_PATH}"
            ls -1 "${PLAYWRIGHT_BROWSERS_PATH}" || true
          else
            echo "[PW_CACHE] Missing: ${PLAYWRIGHT_BROWSERS_PATH}"
          fi
          echo "========================="
        '''
      }
    }

    stage('Prepare Python') {
      steps {
        sh '''
          set -e
          python3 --version
          mkdir -p "${PIP_CACHE_DIR}"
          pybin="${PYTHON_BIN}"

          if [ ! -x "${pybin}" ]; then
            python3 -m venv .venv || true
          fi

          if [ ! -x "${pybin}" ]; then
            python3 -m ensurepip --upgrade || true
            python3 -m venv .venv || true
          fi

          if [ ! -x "${pybin}" ]; then
            if ! python3 -m pip --version >/dev/null 2>&1; then
              if ! python3 -m ensurepip --upgrade >/dev/null 2>&1; then
                curl -fsSL https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py
                python3 /tmp/get-pip.py --user
              fi
            fi
            pybin="python3"
          fi

          echo "${pybin}" > "${PYTHON_BIN_FILE}"
          "${pybin}" --version

          current_hash="$(sha256sum requirements.txt | awk '{print $1}')"
          saved_hash=""
          if [ -f "${REQ_HASH_FILE}" ]; then
            saved_hash="$(cat "${REQ_HASH_FILE}")"
          fi

          need_install=0
          if [ ! -f "${REQ_HASH_FILE}" ]; then
            need_install=1
          fi
          if [ "${current_hash}" != "${saved_hash}" ]; then
            need_install=1
          fi
          if ! "${pybin}" -m pytest --version >/dev/null 2>&1; then
            need_install=1
          fi

          if [ "${need_install}" = "1" ]; then
            echo "Installing Python dependencies (first run or requirements changed)..."
            "${pybin}" -m pip install --upgrade pip
            "${pybin}" -m pip install -r requirements.txt
            echo "${current_hash}" > "${REQ_HASH_FILE}"
          else
            echo "Python dependencies already installed, skip pip install."
          fi
        '''
      }
    }

    stage('Prepare Playwright cache') {
      steps {
        sh '''
          set -e
          mkdir -p "${PLAYWRIGHT_BROWSERS_PATH}"
          echo "PLAYWRIGHT_BROWSERS_PATH=${PLAYWRIGHT_BROWSERS_PATH}"
          ls -la "${PLAYWRIGHT_BROWSERS_PATH}" || true
        '''
      }
    }

    stage('Install missing Playwright browsers') {
      steps {
        sh '''
          set -e
          pybin="$(cat "${PYTHON_BIN_FILE}")"
          need_chromium=0
          need_firefox=0
          need_webkit=0

          if [ "${RUN_CHROMIUM}" = "true" ] || [ "${RUN_MOBILE_CHROMIUM}" = "true" ]; then
            need_chromium=1
          fi
          if [ "${RUN_FIREFOX}" = "true" ]; then
            need_firefox=1
          fi
          if [ "${RUN_WEBKIT}" = "true" ] || [ "${RUN_MOBILE_WEBKIT}" = "true" ]; then
            need_webkit=1
          fi

          if [ "${need_chromium}" = "1" ]; then
            if ls "${PLAYWRIGHT_BROWSERS_PATH}"/chromium-* >/dev/null 2>&1; then
              echo "Chromium already exists in shared cache."
            else
              "${pybin}" -m playwright install chromium
            fi
          fi

          if [ "${need_firefox}" = "1" ]; then
            if ls "${PLAYWRIGHT_BROWSERS_PATH}"/firefox-* >/dev/null 2>&1; then
              echo "Firefox already exists in shared cache."
            else
              "${pybin}" -m playwright install firefox
            fi
          fi

          if [ "${need_webkit}" = "1" ]; then
            if ls "${PLAYWRIGHT_BROWSERS_PATH}"/webkit-* >/dev/null 2>&1; then
              echo "WebKit already exists in shared cache."
            else
              "${pybin}" -m playwright install webkit
            fi
          fi
        '''
      }
    }

    stage('Run provider matrix') {
      steps {
        script {
          def runMatrix = {
            sh '''
          set -e
          pybin="$(cat "${PYTHON_BIN_FILE}")"

          rm -rf allure-results allure-results-* || true
          mkdir -p allure-results

          providers=""
          case "${PROVIDER_SCOPE}" in
            all) providers="mts beeline megafon t2 rostelecom domru" ;;
            smoke) providers="domru t2" ;;
            *) providers="${PROVIDER_SCOPE}" ;;
          esac

          run_one() {
            provider="$1"
            mode="$2"
            browser="$3"
            profile="$4"
            suffix="$5"

            PYTEST_ARGS="test_universal2.py --alluredir=allure-results-${mode}-${suffix} --timeout=600 -s --service-mode=${mode} --browser=${browser} --blocking-profile=${BLOCKING_PROFILE} --provider=${provider}"
            if [ -n "${SITE}" ]; then
              PYTEST_ARGS="${PYTEST_ARGS} --site=${SITE}"
            fi
            if [ -n "${profile}" ]; then
              PYTEST_ARGS="${PYTEST_ARGS} --execution-profile=${profile}"
            fi

            echo "Running: provider=${provider} mode=${mode} browser=${browser} profile=${profile:-desktop}"
            echo "Pytest args: ${PYTEST_ARGS}"
            "${pybin}" -m pytest ${PYTEST_ARGS}
          }

          for provider in ${providers}; do
            echo "==================================================="
            echo "Provider: ${provider}"
            echo "==================================================="

            if [ "${RUN_CHROMIUM}" = "true" ]; then
              if [ "${SERVICE_MODE}" = "core" ] || [ "${SERVICE_MODE}" = "all" ]; then
                run_one "${provider}" "core" "chromium" "" "chromium"
              fi
              if [ "${SERVICE_MODE}" = "variants" ] || [ "${SERVICE_MODE}" = "all" ]; then
                run_one "${provider}" "variants" "chromium" "" "chromium"
              fi
            fi

            if [ "${RUN_FIREFOX}" = "true" ]; then
              if [ "${SERVICE_MODE}" = "core" ] || [ "${SERVICE_MODE}" = "all" ]; then
                run_one "${provider}" "core" "firefox" "" "firefox"
              fi
              if [ "${SERVICE_MODE}" = "variants" ] || [ "${SERVICE_MODE}" = "all" ]; then
                run_one "${provider}" "variants" "firefox" "" "firefox"
              fi
            fi

            if [ "${RUN_WEBKIT}" = "true" ]; then
              if [ "${SERVICE_MODE}" = "core" ] || [ "${SERVICE_MODE}" = "all" ]; then
                run_one "${provider}" "core" "webkit" "" "webkit"
              fi
              if [ "${SERVICE_MODE}" = "variants" ] || [ "${SERVICE_MODE}" = "all" ]; then
                run_one "${provider}" "variants" "webkit" "" "webkit"
              fi
            fi

            if [ "${RUN_MOBILE_CHROMIUM}" = "true" ]; then
              if [ "${SERVICE_MODE}" = "core" ] || [ "${SERVICE_MODE}" = "all" ]; then
                run_one "${provider}" "core" "chromium" "mobile-chromium" "mobile-chromium"
              fi
              if [ "${SERVICE_MODE}" = "variants" ] || [ "${SERVICE_MODE}" = "all" ]; then
                run_one "${provider}" "variants" "chromium" "mobile-chromium" "mobile-chromium"
              fi
            fi

            if [ "${RUN_MOBILE_WEBKIT}" = "true" ]; then
              if [ "${SERVICE_MODE}" = "core" ] || [ "${SERVICE_MODE}" = "all" ]; then
                run_one "${provider}" "core" "webkit" "mobile-webkit" "mobile-webkit"
              fi
              if [ "${SERVICE_MODE}" = "variants" ] || [ "${SERVICE_MODE}" = "all" ]; then
                run_one "${provider}" "variants" "webkit" "mobile-webkit" "mobile-webkit"
              fi
            fi
          done

          for d in allure-results-*; do
            if [ -d "${d}" ]; then
              cp -R "${d}"/. allure-results/
            fi
          done
        '''
          }

          if (params.USE_TELEGRAM_PROXY) {
            withCredentials([
              string(credentialsId: 'telegram_proxy_url', variable: 'TELEGRAM_PROXY_URL'),
              string(credentialsId: 'telegram_proxy_auth_secret', variable: 'TELEGRAM_PROXY_AUTH_SECRET'),
              string(credentialsId: 'tg_proxy_creds_survarius', variable: 'TELEGRAM_PROXY_CREDS')
            ]) {
              echo 'Telegram proxy credentials loaded from Jenkins credentials store.'
              runMatrix()
            }
          } else {
            echo 'Telegram proxy disabled by parameter.'
            runMatrix()
          }
        }
      }
    }
  }

  post {
    always {
      archiveArtifacts artifacts: 'allure-results/**, allure-results-*/**, telegram_message.txt, telegram_should_send.txt, notify_state.json', allowEmptyArchive: true
      script {
        try {
          // Requires Jenkins Allure plugin. If not installed, continue without failing the build.
          allure includeProperties: false, jdk: '', results: [[path: 'allure-results']]
          echo 'Allure report published in Jenkins UI.'
        } catch (Exception e) {
          echo "Allure publish skipped: ${e.getMessage()}"
        }
      }
      script {
        def notifySummary = {
          sh '''
            set +e
            pybin="python3"
            if [ -f "${PYTHON_BIN_FILE}" ]; then
              pybin="$(cat "${PYTHON_BIN_FILE}")"
            fi
            if [ ! -x "${pybin}" ] && [ "${pybin}" != "python3" ]; then
              pybin="python3"
            fi

            export ALLURE_RESULTS_DIR="allure-results"
            export RUN_URL="${BUILD_URL}"
            export ALLURE_URL="${BUILD_URL}allure/"

            "${pybin}" notify_from_allure.py || {
              echo "notify_from_allure.py failed, skip summary alert."
              exit 0
            }

            if [ ! -f telegram_should_send.txt ]; then
              echo "telegram_should_send.txt missing, skip summary alert."
              exit 0
            fi
            if [ "$(cat telegram_should_send.txt | tr -d '[:space:]')" != "1" ]; then
              echo "Summary alert disabled by notify rules."
              exit 0
            fi
            if [ ! -s telegram_message.txt ]; then
              echo "telegram_message.txt is empty, skip summary alert."
              exit 0
            fi

            "${pybin}" - <<'PY'
from pathlib import Path
from test_universal2 import send_telegram_alert

text = Path("telegram_message.txt").read_text(encoding="utf-8").strip()
if not text:
    raise SystemExit(0)

ok = send_telegram_alert(text, alert_type="summary")
raise SystemExit(0 if ok else 2)
PY
            send_rc=$?
            if [ "${send_rc}" -ne 0 ]; then
              echo "Summary alert was not delivered (check TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID and proxy)."
            fi
            exit 0
          '''
        }

        if (params.USE_TELEGRAM_PROXY) {
          withCredentials([
            string(credentialsId: 'telegram_proxy_url', variable: 'TELEGRAM_PROXY_URL'),
            string(credentialsId: 'telegram_proxy_auth_secret', variable: 'TELEGRAM_PROXY_AUTH_SECRET'),
            string(credentialsId: 'tg_proxy_creds_survarius', variable: 'TELEGRAM_PROXY_CREDS')
          ]) {
            notifySummary()
          }
        } else {
          notifySummary()
        }
      }
      echo "Build URL: ${env.BUILD_URL}"
    }
  }
}
