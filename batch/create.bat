:: ENTER PATH WHERE THE script.py IS LOCATED.
cd C:\Users\David E\version-control\ProjectCreationAutomation

python script.py %1 %2 %3

:: ENTER PATH WHERE YOUR PROJECTS ARE SAVED
:: e.g. C:\Users\<USERNAME>\Documents\Projects
cd C:\Users\David E\version-control\%1


git init

::ENTER YOUR GIT USERNAME
git remote rm origin
git remote add origin https://github.com/mevorahde/%1.git

echo # %1 > README.md
git add .
git commit -m "initial commit"
git push -u origin master

:: NO PARM TO OPEN IDE
IF %3== not defined (CONTINUE)

:: OPENS PYCHARM
IF %3==pycharm (pycharm64 .) 

:: OPENS VISUAL STUDIO
IF %3==visualstudio (devenv.exe .)

:: OPENS SUBLIME
IF %3==sublime (subl .)

:: OPENS VISUAL STUDIO CODE
IF %3==vsc (code .)


