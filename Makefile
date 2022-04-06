
# Add the following 'help' target to your Makefile
# And add help text after each target name starting with '\#\#'
.PHONY: help
help: ## This help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

.PHONY: clean
clean: clean-build clean-pyc ## remove all build, test, coverage and Python artifacts

.PHONY: clean-build
clean-build: ## remove build artifacts
	rm -fr bin/
	rm -fr include/
	rm -fr lib/
	rm -fr lib64/
	rm -fr build/
	rm -fr dist/
	rm -fr .eggs/
	find . -name '*.egg-info' -exec rm -fr {} +
	find . -name '*.egg' -exec rm -f {} +


.PHONY: clean-pyc
clean-pyc: ## remove Python file artifacts
	find . -name '*.pyc' -exec rm -f {} +
	find . -name '*.pyo' -exec rm -f {} +
	find . -name '*~' -exec rm -f {} +
	find . -name '__pycache__' -exec rm -fr {} +

bin/python: ## Install Python virtualenv
	@echo "Creating virtualenv"
	python3 -m venv .
	./bin/pip install -U pip
	./bin/pip install -r requirements.txt

.PHONY: setup
setup: bin/python ## Setup environment
	@echo "Updating packages"
	./bin/pip install -U pip
	./bin/pip install -r requirements.txt

.PHONY: format
format: bin/python  ## Format tests
	@echo "Formating code"
	./bin/black tests
	./bin/isort tests

.PHONY: prepare-containers
prepare-containers: ## Get container images
	@docker-compose build

.PHONY: start-containers
start-containers: ## Start containers
	@docker-compose up -d && sleep 10

.PHONY: reload-varnish-config
reload-varnish-config: ## Start containers
	@docker-compose exec varnish varnishreload

.PHONY: stop-containers
stop-containers: ## Stop containers
	@docker-compose down

.PHONY: tests
tests: ## Stop containers
	bin/pytest tests

.PHONY: run
run: bin/python prepare-containers ## Run application
	@echo "Starting containers (wait 10 seconds to everything to be up)"
	make start-containers
	@echo "Running exploit"
	bin/pytest tests
	@echo "Stopping containers"
	make stop-containers

.PHONY: all
all: clean setup run ## Initialize the environment and run the report
