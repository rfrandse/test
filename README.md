# Purpose

Generate information on next-steps for outstanding Gerrit commits per
the OpenBMC merge policies.
This script originated from
https://github.com/williamspatrick/gerrit-report
and converted to run in python2 
Additionally reports are sent via slack to openbmc team members

# Requirements

1. python2
2. An ssh alias to Gerrit `openbmc.gerrit`
3. https://github.com/os/slacker module installed. 
4. config.py file with 
    #!/usr/bin/python
    token = "<insert slack token here>"

# Usages

## Default use

Generate a report for all commits untouched in the last day:

```
gerrit-report.py --protocol slack report
gerrit-report.py --protocol irc report
```

## Individual developer

List the current status on all your own commits.

```gerrit-report.py --age=0d --owner=<github_id> report```

## Team lead

List the current status of your teams commits.

```gerrit-report.py --age=0d --owner=<github0> --owner=<github1> ... report```

This has the effect of a Gerrit query such as
`(owner:github0 OR owner:github1)`.

