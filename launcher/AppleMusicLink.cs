// Lanceur d'AppleMusicLink : met l'appli à jour depuis GitHub, installe Python s'il manque, puis lance l'appli.
// Compilation : build.bat (compilateur C# fourni avec Windows, rien à installer).
using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.IO.Compression;
using System.Net;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Windows.Forms;
using Microsoft.Win32;

[assembly: AssemblyTitle("AppleMusicLink")]
[assembly: AssemblyProduct("AppleMusicLink")]
[assembly: AssemblyCompany("MrReLaX")]
[assembly: AssemblyVersion("1.0.0.0")]

static class Lanceur
{
    const string DEPOT = "https://github.com/MrReLaX1/AppleMusicLink";
    const string PYTHON_URL = "https://www.python.org/ftp/python/3.14.5/python-3.14.5-amd64.exe";
    const string PYTHON_SHA256 = "F9C09F5ED6F796FD1A8BC5DDFA41715A494B453C4781F0E35D5077CF9FA58F6D";  // python.org, signé PSF
    const string IMPORTS = "import pycaw, PIL, winrt.windows.media.control, winrt.windows.storage.streams";

    // les variables AMLINK_* servent à tester sans GitHub ni toucher à l'installation réelle
    static readonly string Source = Env("AMLINK_SOURCE", "https://raw.githubusercontent.com/MrReLaX1/AppleMusicLink/main/");
    static readonly string ZipUrl = Env("AMLINK_ZIP", DEPOT + "/archive/refs/heads/main.zip");
    static readonly string Racine = Env("AMLINK_RACINE", Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "AppleMusicLink"));
    static readonly string DossierApp = Path.GetFullPath(Path.Combine(Racine, "app"));
    static readonly string Journal = Path.Combine(Racine, "installation.log");
    static readonly object Verrou = new object();
    static Form fenetre;
    static Label statut;

    [DllImport("user32.dll")]
    static extern bool SetProcessDPIAware();

    [STAThread]
    static void Main()
    {
        ServicePointManager.SecurityProtocol = SecurityProtocolType.Tls12;
        SetProcessDPIAware();
        Application.EnableVisualStyles();
        fenetre = CreerFenetre();
        fenetre.Shown += delegate { new Thread(Travailler) { IsBackground = true }.Start(); };
        Application.Run(fenetre);
    }

    static void Travailler()
    {
        try
        {
            Directory.CreateDirectory(Racine);
            string locale = LireVersion();
            Statut("Recherche de mises à jour…");
            string distante = null;
            try { distante = Telecharger(Source + "app/VERSION").Trim(); }
            catch (WebException e) { Log("GitHub injoignable : " + e.Message); }
            if (locale == null && distante == null)
                throw new Exception("Impossible de joindre GitHub pour la première installation. Vérifie ta connexion internet.");
            bool nouvelle = distante != null && (locale == null || new Version(distante) > new Version(locale));
            if (nouvelle)
            {
                Statut(locale == null ? "Téléchargement d'AppleMusicLink " + distante + "…" : "Mise à jour " + locale + " → " + distante + "…");
                InstallerApp();
            }

            string python = TrouverPython();
            if (python == null)
            {
                Statut("Installation de Python 3.14 (première fois, 1 à 2 minutes)…");
                InstallerPython();
                python = TrouverPython();
                if (python == null) throw new Exception("Python s'est installé mais reste introuvable.");
            }
            if (nouvelle || !ImportsOk(python))
            {
                Statut("Installation des composants (première fois, environ 1 minute)…");
                Executer(Path.Combine(python, "python.exe"), "-m pip install --user --disable-pip-version-check --no-warn-script-location -r \""
                         + Path.Combine(DossierApp, "requirements.txt") + "\"", 600000);
                if (!ImportsOk(python)) throw new Exception("Les composants Python n'ont pas pu s'installer.\nDétails : " + Journal);
            }

            Statut("Lancement…");
            Log("> pythonw fh6_volume.py");
            Process.Start(new ProcessStartInfo(Path.Combine(python, "pythonw.exe"), "\"" + Path.Combine(DossierApp, "fh6_volume.py") + "\"")
            { WorkingDirectory = DossierApp, UseShellExecute = false });
            Thread.Sleep(800);
            fenetre.BeginInvoke((Action)fenetre.Close);
        }
        catch (Exception e)
        {
            Log("ERREUR : " + e);
            fenetre.Invoke((Action)delegate
            {
                MessageBox.Show(fenetre, e.Message, "AppleMusicLink", MessageBoxButtons.OK, MessageBoxIcon.Error);
                fenetre.Close();
            });
        }
    }

    static string LireVersion()
    {
        string f = Path.Combine(DossierApp, "VERSION");
        return File.Exists(f) && File.Exists(Path.Combine(DossierApp, "fh6_volume.py")) ? File.ReadAllText(f).Trim() : null;
    }

    static void InstallerApp()
    {
        string zip = Path.Combine(Racine, "maj.zip");
        TelechargerFichier(ZipUrl, zip);
        Directory.CreateDirectory(DossierApp);
        using (ZipArchive archive = ZipFile.OpenRead(zip))
        {
            ZipArchiveEntry version = null;
            foreach (ZipArchiveEntry entree in archive.Entries)
            {
                // archive GitHub : « AppleMusicLink-main/app/… » ; seul le dossier app/ est installé
                string[] parties = entree.FullName.Split(new[] { '/' }, 3);
                if (parties.Length < 3 || parties[1] != "app" || entree.Name.Length == 0) continue;
                string cible = Path.GetFullPath(Path.Combine(DossierApp, parties[2]));
                if (!cible.StartsWith(DossierApp + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase)) continue;
                if (entree.Name.Equals("reglages.json", StringComparison.OrdinalIgnoreCase)) continue;  // on garde ceux de l'utilisateur
                if (parties[2] == "VERSION") { version = entree; continue; }
                Directory.CreateDirectory(Path.GetDirectoryName(cible));
                entree.ExtractToFile(cible, true);
            }
            if (version == null) throw new Exception("Archive GitHub incomplète (app/VERSION manquant).");
            version.ExtractToFile(Path.Combine(DossierApp, "VERSION"), true);  // en dernier : une mise à jour coupée sera refaite
        }
        File.Delete(zip);
    }

    static string TrouverPython()
    {
        foreach (RegistryHive ruche in new[] { RegistryHive.CurrentUser, RegistryHive.LocalMachine })
        using (RegistryKey racine = RegistryKey.OpenBaseKey(ruche, RegistryView.Registry64))
        using (RegistryKey cle = racine.OpenSubKey(@"Software\Python\PythonCore\3.14\InstallPath"))  // la version testée
        {
            string dossier = cle == null ? null : cle.GetValue("") as string;
            if (dossier != null && File.Exists(Path.Combine(dossier, "pythonw.exe"))) return dossier;
        }
        return null;
    }

    static void InstallerPython()
    {
        string exe = Path.Combine(Racine, "python-3.14.5-amd64.exe");
        TelechargerFichier(PYTHON_URL, exe);
        using (SHA256 sha = SHA256.Create())
        using (FileStream f = File.OpenRead(exe))
            if (!BitConverter.ToString(sha.ComputeHash(f)).Replace("-", "").Equals(PYTHON_SHA256, StringComparison.OrdinalIgnoreCase))
                throw new Exception("Le programme d'installation de Python téléchargé ne correspond pas à l'officiel. Installation annulée.");
        int code = Executer(exe, "/quiet InstallAllUsers=0 Include_launcher=0 Include_test=0 Include_doc=0 Shortcuts=0 AssociateFiles=0", 900000);
        File.Delete(exe);
        if (code != 0) throw new Exception("L'installation de Python a échoué (code " + code + ").\nDétails : " + Journal);
    }

    static bool ImportsOk(string python)
    {
        return Executer(Path.Combine(python, "python.exe"), "-c \"" + IMPORTS + "\"", 60000) == 0;
    }

    static int Executer(string exe, string args, int delaiMs)
    {
        Log("> " + exe + " " + args);
        ProcessStartInfo psi = new ProcessStartInfo(exe, args)
        { UseShellExecute = false, CreateNoWindow = true, RedirectStandardOutput = true, RedirectStandardError = true };
        using (Process p = Process.Start(psi))
        {
            p.OutputDataReceived += (s, e) => { if (e.Data != null) Log(e.Data); };
            p.ErrorDataReceived += (s, e) => { if (e.Data != null) Log(e.Data); };
            p.BeginOutputReadLine();
            p.BeginErrorReadLine();
            if (!p.WaitForExit(delaiMs)) { p.Kill(); throw new Exception("Trop long : " + Path.GetFileName(exe)); }
            p.WaitForExit();
            Log("< code " + p.ExitCode);
            return p.ExitCode;
        }
    }

    static WebClient Client()
    {
        WebClient c = new WebClient { Encoding = Encoding.UTF8 };
        c.Headers[HttpRequestHeader.UserAgent] = "AppleMusicLink";
        return c;
    }

    static string Telecharger(string url)
    {
        if (url.StartsWith("http")) url += "?t=" + DateTime.UtcNow.Ticks;  // contourne le cache de GitHub
        using (WebClient c = Client()) return c.DownloadString(url);
    }

    static void TelechargerFichier(string url, string fichier)
    {
        Log("téléchargement " + url);
        using (WebClient c = Client()) c.DownloadFile(url, fichier);
    }

    static string Env(string nom, string defaut)
    {
        string v = Environment.GetEnvironmentVariable(nom);
        return string.IsNullOrEmpty(v) ? defaut : v;
    }

    static void Log(string ligne)
    {
        lock (Verrou)
            try { File.AppendAllText(Journal, DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss ") + ligne + Environment.NewLine); }
            catch (IOException) { }
    }

    static void Statut(string texte)
    {
        Log(texte);
        fenetre.BeginInvoke((Action)delegate { statut.Text = texte; });
    }

    static Form CreerFenetre()
    {
        Color fond = Color.FromArgb(10, 10, 18), rose = Color.FromArgb(255, 45, 135), doux = Color.FromArgb(157, 155, 180);
        Form f = new Form
        {
            Text = "AppleMusicLink", FormBorderStyle = FormBorderStyle.FixedSingle, MaximizeBox = false,
            StartPosition = FormStartPosition.CenterScreen, BackColor = fond, ForeColor = Color.FromArgb(243, 242, 248),
            Font = new Font("Segoe UI", 10f), AutoScaleDimensions = new SizeF(96f, 96f), AutoScaleMode = AutoScaleMode.Dpi,
            ClientSize = new Size(460, 140)
        };
        try { f.Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath); }
        catch (ArgumentException) { }
        Label titre = new Label { Text = "AppleMusicLink", Font = new Font("Segoe UI Semibold", 16f), ForeColor = rose, AutoSize = true, Location = new Point(20, 14) };
        Label sous = new Label { Text = "Apple Music × Forza Horizon 6", ForeColor = doux, AutoSize = true, Location = new Point(22, 50) };
        statut = new Label { Text = "Démarrage…", AutoSize = false, Location = new Point(20, 82), Size = new Size(420, 24) };
        ProgressBar barre = new ProgressBar { Style = ProgressBarStyle.Marquee, MarqueeAnimationSpeed = 25, Location = new Point(20, 114), Size = new Size(420, 8) };
        f.Controls.AddRange(new Control[] { titre, sous, statut, barre });
        f.FormClosed += delegate { Environment.Exit(0); };
        return f;
    }
}
