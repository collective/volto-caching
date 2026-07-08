### Defensive settings for make:
#     https://tech.davis-hansson.com/p/make/
SHELL:=bash
.ONESHELL:
.SHELLFLAGS:=-xeu -o pipefail -O inherit_errexit -c
.SILENT:
.DELETE_ON_ERROR:
MAKEFLAGS+=--warn-undefined-variables
MAKEFLAGS+=--no-builtin-rules

# We like colors
# From: https://coderwall.com/p/izxssa/colored-makefile-for-golang-projects
RED=`tput setaf 1`
GREEN=`tput setaf 2`
RESET=`tput sgr0`
YELLOW=`tput setaf 3`

# Python checks
UV?=uv

# installed?
ifeq (, $(shell which $(UV) ))
  $(error "UV=$(UV) not found in $(PATH)")
endif

ROOT_FOLDER=$(shell dirname $(realpath $(firstword $(MAKEFILE_LIST))))
VENV_FOLDER=$(ROOT_FOLDER)/.venv
export VIRTUAL_ENV=$(VENV_FOLDER)
export PLONE_VERSION := 6.2.1
export VOLTO_VERSION := 19.1.4

# Add the following 'help' target to your Makefile
# And add help text after each target name starting with '\#\#'
.PHONY: help
help: ## This help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

.PHONY: clean
clean: ## Clean environment
	@echo "$(RED)==> Cleaning environment and build$(RESET)"
	rm -rf $(VENV_FOLDER) .python-version .venv .*_cache uv.lock

$(VENV_FOLDER): ## Install dependencies
	@echo "$(GREEN)==> Install environment$(RESET)"
	@uv sync

.PHONY: install
install: $(VENV_FOLDER) ## Install the project

############################################
# QA
############################################
.PHONY: lint
lint: $(VENV_FOLDER) ## Check code base according to our standards
	@echo "$(GREEN)==> Lint codebase$(RESET)"
	@uvx ruff@latest check --fix --config $(ROOT_FOLDER)/pyproject.toml

.PHONY: format
format: ## Check and fix code base according to Plone standards
	@echo "$(GREEN)==> Format codebase$(RESET)"
	@uvx ruff@latest check --select I --fix --config $(ROOT_FOLDER)/pyproject.toml
	@uvx ruff@latest format --config $(ROOT_FOLDER)/pyproject.toml

############################################
# Containers
############################################

.PHONY: containers-prepare
containers-prepare: ## Get container images
	@echo "$(GREEN)==> Getting container images $(RESET)"
	@docker compose build
	@docker compose pull

.PHONY: containers-start
containers-start: ## Start containers
	@echo "$(GREEN)==> Starting containers $(RESET)"
	@docker compose up -d && sleep 10

.PHONY: reload-varnish-config
reload-varnish-config: ## Reload Varnish configuration
	@echo "$(GREEN)==> Reloading Varnish configuration $(RESET)"
	@docker compose exec varnish varnishreload

.PHONY: containers-stop
containers-stop: ## Stop containers
	@echo "$(GREEN)==> Stopping containers $(RESET)"
	@docker compose down

############################################
# Tests
############################################
.PHONY: test
test: $(VENV_FOLDER) ## Run tests
	@echo "$(GREEN)==> Running tests $(RESET)"
	@uv run pytest $(filter-out $@ --,$(MAKECMDGOALS))

.PHONY: all
all: clean install containers-prepare ## Initialize the environment and run the report
	@echo "$(GREEN)==> Running tests $(RESET)"
	@make test


############################################
# Changelog
############################################
.PHONY: changelog
changelog: $(VENV_FOLDER) ## Display a draft of the changelog
	@echo "🚀 Display the draft for the changelog"
	@uv run towncrier --draft --version dummy
