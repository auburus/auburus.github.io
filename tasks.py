from invoke import task


@task
def build(c):
	c.run('python -m markdown -x extra index.md > index.html', pty=True)
