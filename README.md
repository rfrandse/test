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
```    
#!/usr/bin/python
    token = "<insert slack token here>"
```
# Usages

## Default use

```
gerrit-report2.py -sm -stat report

-sm    send slack message
-stat  sent statistics to slack
```

