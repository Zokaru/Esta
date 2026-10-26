# Esta
Minimal Static Site Generator

## About

Esta is a simple Python script with the bare minimum needed to develop and deploy **static websites made in pure HTML/CSS/JS**.

Esta is **minimal by design:** lightweight, performant, and easy to setup (zero dependencies besides Python itself).

Esta's use case is developing **simple websites** that have minimal server-side work and aren't updated too frequently: **your average personal website, portfolio, or small business page.** As a rule of thumb, if your server-side code is limited to a simple contact form, and you don't need to upload a blog post every other day, then Esta is for you.

Esta is built for for **Github Pages** and similar services. I created it for my personal website, https://zokaru.github.io/.

### Features

- Templates with nesting and custom attributes.
- Simple localisation.
- Cache-friendly asset management.
- CSS and JS bundling and minifying.
- Routing.
- Basic syntax check for HTML and CSS.

## Requirements

- Python 3.7^

## Installation

Assuming you have [Python](https://www.python.org/) and [PyPI](https://www.python.org/) installed, run:

`pip install esta@git+https://github.com/Zokaru/Esta`

## Quick start

1. Run `python esta.py new DIR`, with DIR being the location where you want to create your project (leave blank to install in your current directory).
2. Edit the `base_url` in the generated config file (config.ini) according to your needs.
3. Run `python esta.py build` to build your project.

## Usage

The following is an extensive guide of all concepts, features and tools included:

### Config file

The configuration file (**config.ini** by default) contains all settings needed to control the build process of your project. It has the following sections:

- General: Change the base URL of your project, which is used when generating all internal links.
- Paths: You can customise which directories the build command will use: where's the base directory, translation files, templates, and more. This lets you use any project structure you want instead of the default.
- Lang: List all languages your website supports.
- CSS: Specify all CSS files to include. The order in which you list the files is honoured when bundling.
- JS: Same as CSS, but for JavaScript files.

> Note: You can have multiple configuration files in a single project; just run `python esta.py build -c PATH_TO_CONFIG_FILE` to specify which file to use.

### Source

The 'source' directory you defined in the config file represents the root directory of your website.

This directory must include an index.html page, which in most cases should have a language selector and/or a redirect.

Your sitemap, .htaccess, and robots.txt files should also be located here. All files in the root 'source' directory will be copied as-is to the root directory of your build (folders are ignored).

### Pages

These are the actual HTML pages of your website. The folder/file structure you define in the 'pages' directory will be the URL structure of the built website.

### Templates

These are your 'components': **HTML files containing code intended to be reused.** Your site's layout, header, and footer are some common use cases for the template system.

Store templates as HTML files in the 'templates' directory you defined in the config file.

Use templates by using the `<esta-template>` tag:

```html
<esta-template template="name"></esta-template>
```

With `name` being the filename (without extension) of the HTML template located in your 'templates' folder.

#### Nesting

You can freely include templates inside other templates. Recursive nesting is unsupported, as well as nesting too deeply (more than 10 levels) for performance reasons.

#### Content

Templates can act as containers for other HTML content, by using the `<esta-content>` tag. For example, let's say we have a template called blog-post.html with the following contents:

```html
<article class="post">
    <esta-content>
</article>
```

When instancing the template, we can add any HTML content like this:

```html
<esta-template template="blog-post">
    <h3>Title</h3>
    <p>Lorem ipsum</p>
</esta-template>
```

And the final result will be:

```html
<article class="post">
    <h3>Title</h3>
    <p>Lorem ipsum</p>
</article>
```

#### Attributes

You can also pass values to a template by using attributes. For example, let's say we have a template called heading.html with the following contents:

```html
<div class="heading {{ theme }}">
    <h1>{{ text }}</h1>
</div>
```

We can reference 'theme' and 'text' when we instance the template like this:

```html
<esta-template template="heading" theme="dark" text="{{ t: 'contact.title' }}"></esta-template>
```

And the final result will be:

```html
<div class="heading dark">
    <h1>Contact</h1>
</div>
```

Where did the text 'Contact' came from? By using the next feature: translations.

### Translations

Esta builds multi-language websites using subdirectories (e.g. `www.example.com/es/`). This approach is the easiest to implement for small websites, in addition to being SEO-friendly, as explained [here](https://developers.google.com/search/docs/specialty/international/managing-multi-regional-sites#locale-specific-urls).

Multi-language support is handled by using translation files located in the 'lang' folder. **You must make one JSON file for each language you want to support,** named using a BCP 47 language subtag (like en, es, fr, etc). Use a key-based notation for your translations, like in the following example:

```json
{
    "key": "value",
    "hello": "Hello",
    "home": {
        "welcome": "Welcome"
    }
}
```

In order to access keys in templates and pages, use `{{ t: 'key' }}`, with `key` being a key from your translation files.

For example:

```html
<h1>{{ t: 'home.welcome' }}</h1>
```

Will resolve as:

```html
<h1>Welcome</h1> <!-- English -->
<h1>Bienvenido</h1> <!-- Español -->
```

#### Get the current language

Use `{{ lang }}` to get the language the page is being built for, aka the "current" language.

#### Get all languages

Use `{{ langs }}` to get a JSON array containing all available languages as defined in the config file.

> Note: Translations are extremely barebores at the moment, with no support for plural forms, variations by context, or nesting. If you need advanced localisation features, it is recommended to use an external library or framework like [i18next](https://www.i18next.com/).

### Links

Internal links to any HTML document in your website can be resolved automatically.

Add links to internal pages using `{{ page: 'path' }}`, with `path` being the path to an HTML document in your 'pages' folder.

For example:

```html
<a href="{{ page: 'blog/christmas.html' }}"></a>
```

Will resolve as:

```html
<a href="https://mywebsite.com/en/blog/christmas.html"></a>
<!-- In this case, the visitor is accessing the website in English -->
```

> Important: You must set a valid 'base_url' in your config file for this to work correctly.

If you want to specify a language instead of automatically using the current one, add a `lang` parameter:

`{{ page: 'path' lang: 'key' }}`

This is useful for implementing language selectors, for example.

### Assets

Link assets (images, video, fonts, server-side code, etc) by using `{{ asset: 'path' }}`, with `path` being the relative path to a resource located in your 'assets' folder.

Example:

```html
<img src="{{ asset: 'img/sample.jpg' }}">`
```

> Note: Esta manages browser-caching for assets, CSS, and JS files by reading file modification dates and adding hashes to filenames when building.

### CSS

Store CSS files in the 'css' directory you defined in the config file. Esta will automatically bundle them all into a single minified file when building, improving performance by reducing the number of requests and total filesize.

Add the bundled CSS to your code by using the `<esta-css>` tag:

```html
<esta-css />
```

This will create a `<link rel="stylesheet">` tag pointing to the bundled CSS.

### JavaScript

Javascript bundling works identically to CSS: store JS files in the 'js' directory defined in your config file, and link the bundle by using the `<esta-js>` tag:

```html
<esta-js />
```

## License

This project is licensed under the GNU General Public License Version 3: [LICENSE](/LICENSE).
