:: ENTER PATH WHERE THE script.py IS LOCATED.
cd C:\Users\David E\version-control\ProjectCreationAutomation

python script.py %1 %2 %3

:: ENTER PATH WHERE YOUR PROJECTS ARE SAVED
:: e.g. C:\Users\<USERNAME>\Documents\Projects
cd C:\Users\David E\version-control\%1



echo "# -" >> README.md
git init
git remote add origin https://github.com/mevorahde/%1.git
git add README.md
git commit -m "first commit"
git branch -M main
git push -u origin main

:: OPENS PYCHARM
IF %3==pycharm (pycharm64 .)

:: OPENS VISUAL STUDIO
IF %3==visualstudio (devenv.exe .)

:: OPENS SUBLIME
IF %3==sublime (subl .)

:: OPENS VISUAL STUDIO CODE
IF %3==vsc (code .)
