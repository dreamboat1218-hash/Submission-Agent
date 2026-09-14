const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('yibiaoBridge', {
  platform: process.platform,
  registerSkill: (name, skill) => {
    ipcRenderer.send('skill:register', { name, description: skill?.description });
  },
  versions: {
    electron: process.versions.electron,
    chrome: process.versions.chrome,
  },
});
