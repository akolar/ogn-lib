test:
	pytest -v

clean:
	rm -rf dist build **/*.egg-info *.egg-info

publish: clean
	pip install 'twine'
	python setup.py sdist bdist_wheel
	twine upload dist/*
	rm -rf build dist .egg requests.egg-info
