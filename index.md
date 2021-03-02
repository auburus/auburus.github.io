Copy module
===========

Ansible's [copy module](https://docs.ansible.com/ansible/latest/collections/ansible/builtin/copy_module.html)
is one of the most widely used modules for its simplicity. Here is what you
need to just copy a file to a remote server:

```bash
.
├── files
│   └── file.txt
└── playbook.yml

```
```yaml
# playbook.yml
- hosts: all
  tasks:
  - name: Copy file
    ansible.builtin.copy:
      src: "file.txt"
      dest: "/tmp/file.txt"
```

But in this blog post we will explore the main cases for copying files to a
remote server, and see that in every case there is a better alternative than
using _ansible.builtin.copy_

## Configuration files

Typical examples of configuration files could be _sshd.conf_ or _nginx.conf_,
and copying them is just a part of a higher level task such as "secure host"
or "install webserver", usually encapsulated in a role/collection.

After using ansible in deployments for the past couple years, I have noticed
that the configuration file never ends up being deployed as-is, and that some
part of the file needs to change depending on the host/deployment scenario/etc.

This is where the [template module](https://docs.ansible.com/ansible/latest/collections/ansible/builtin/template_module.html)
really shines:

```bash
.
├── templates
│   └── file.txt.j2
└── playbook.yml

```
```yaml
# playbook.yml
- hosts: all
  tasks:
  - name: Copy file
    ansible.builtin.template:
      src: "file.txt.j2"
      dest: "/tmp/file.txt"
```

As we see, its usage looks the same as the _copy module_, but the trick is that
`file.txt.j2` is now a Jinja2 file that has access to all the ansible variables:

```jinja
# file.txt.j2

{% if inventory_hostname == "webserver" %}
This is the webserver

{% else %}
Not the webserver, lets use a different configuration

{% endif %}
```

Nowadays I put every configuration file in the `templates` directory, even if
currently doesn't need any dynamic configuration, and that helps in two ways:
- Avoid future refactor: When[^1] the requirement for the dynamic configuration comes,
  it requires almost no effort to implement, since it is already using the _template module_.
- Consistency: This is the key one for our team. By always using the _template
  module_ for configuration files, we all know where to look for them when opening
  a new role or collection.

[^1] If you ever think "There is no way this file will ever require dynamic
modifications", the Project Manager is already typing the Jira ticket for that to
change.

## Binary files/Directory trees
 
Those are the other kind of files you want to copy to a remote server. Say the
`jar` file or executable that the developers have finished, or a full tree for
your python or ruby application.

In those cases, the ansible module
[is](https://stackoverflow.com/questions/27985334/why-is-copying-a-directory-with-ansible-so-slow)
[slow](https://github.com/ansible/ansible/issues/21513),
despite having [pipelining](https://www.jeffgeerling.com/blog/2017/slow-ansible-playbook-check-ansiblecfg)
enabled.

As those posts suggest, using the
[synchronize module](https://docs.ansible.com/ansible/latest/collections/ansible/posix/synchronize_module.html)
significally speeds up your playbook, by leveraging rsync instead of scp, as we'll see
in the following quick benchmark:

```shell
$ tree -h
.
├  [  84]  ansible.cfg
├  [  60]  files
│   └ [ 68M]  bigfile.txt
├  [ 383]  playbook_copy.yml
└  [ 425]  playbook_sync.yml
```
```ini
# ansible.cfg
[defaults]
callback_whitelist = profile_tasks
```
The first playbook, using plain old copy, shows this results:
```yaml
# playbook_copy.yml
---
- hosts: all
  gather_facts: false
  tasks:
    - name: remove file
      ansible.builtin.file:
        path: "/tmp/bigfile.txt"
        state: absent

    - name: copy file
      ansible.builtin.copy:
        src: "bigfile.txt"
        dest: "/tmp/bigfile.txt"

    - name: copy file (again)
      ansible.builtin.copy:
        src: "bigfile.txt"
        dest: "/tmp/bigfile.txt"
```
```bash
copy file ----------------------------------------------------- 81.03s
copy file (again) ---------------------------------------------- 7.88s
remove file ---------------------------------------------------- 4.84s
```
While the same thing, using syncrhonize:
```yaml
# playbook_sync.yml
---
- hosts: all
  gather_facts: false
  tasks:
    - name: remove file
      ansible.builtin.file:
        path: "/tmp/bigfile.txt"
        state: absent

    - name: sync
      ansible.posix.synchronize:
        src: "bigfile.txt"
        dest: "/tmp/bigfile.txt"
        checksum: true

    - name: sync (again)
      ansible.posix.synchronize:
        src: "bigfile.txt"
        dest: "/tmp/bigfile.txt"
        checksum: true
```
```bash
sync ---------------------------------------------------------- 45.84s
remove file ---------------------------------------------------- 4.97s
sync (again) --------------------------------------------------- 4.17s
```
So we see that is about half the time, if we stick to the "regular" values
of those modules. Just that makes it that, by default, we prefer to use
the synchronize module.

### Bonus: Can we make copy any faster?
Two main tricks are recommended to speed it up: Use pipelining (that is an
ansible best practice in general) and set `force: false` in the copy module.

```ini
# ansible.cfg
[defaults]
callback_whitelist = profile_tasks

[connection]
pipelining = true
```
```yaml
# playbook_copy.yml
---
- hosts: all
  gather_facts: false
  tasks:
    - name: remove file
      ansible.builtin.file:
        path: "/tmp/bigfile.txt"
        state: absent

    - name: copy file
      ansible.builtin.copy:
        src: "bigfile.txt"
        dest: "/tmp/bigfile.txt"
        force: false

    - name: copy file (again)
      ansible.builtin.copy:
        src: "bigfile.txt"
        dest: "/tmp/bigfile.txt"
        force: false
```
```bash
copy file ----------------------------------------------------- 71.48s
remove file ---------------------------------------------------- 3.66s
copy file (again) ---------------------------------------------- 2.26s
```
Which saved ~10 sec compared to the original playbook, but is still
significantly slower than synchronize.