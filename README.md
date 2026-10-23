# Esta
Minimal Static Site Generator

## About

Esta is a simple Python script with the bare minimum needed to develop and deploy static websites made in pure HTML/CSS/JS.

Esta is minimal by design: lightweight, performant, and easy to setup (zero dependencies besides Python itself).

Esta's use case is developing simple websites that don't rely too much on server-side code and/or aren't updated too frequently: personal websites, portfolios, and small businesses. As a rule of thumb, if your server-side code is limited to a simple contact form, and you don't need to upload a blog post every day, then Esta is for you.

Esta is ideal for Github Pages and similar services. I created it for my personal website, https://zokaru.github.io/.

### Features

- Templates with nesting and custom attributes.
- Simple localisation.
- Cache-friendly asset management.
- CSS and JS bundling.
- Routing.
- Basic syntax check for HTML and CSS.

## Requirements

- Python 3

## Installation

1. If you don't have it, install Python 3 (https://www.python.org/).
2. Create a config file using the included [config.ini.sample](/config.ini.sample) as reference.
3. Create an 'index.html' file in your 'source' directory.
4. Run `python esta.py build -c CONFIG_FILE`, with CONFIG_FILE being the location of your config file.

## Usage

The following is an extensive guide of all concepts, features and tools included:

### Source

The 'source' directory you defined in the config file represents the root directory of your website.

You must include a index.html page



Your sitemap, .htaccess, and robots.txt files should also be located here. All files in the root 'source' directory will be copied as-is to the root directory of your build (folders are ignored).

### Pages

These are the actual HTML pages of your website. The folder/file structure you define in the 'pages' directory will be the URL structure of the built website.

### Templates

These are your 'components': HTML files containing code intended to be reused. Your site's layout, header, and footer are some common use cases for the template system.

Store templates as HTML files in the 'templates' directory you defined in the config file.

Use templates by using the `<esta-template>` tag:

```html
<esta-template template="name"></esta-template>
```

with `name` being the filename (without extension) of the HTML template located in your 'templates' folder.

#### Nesting

You can freely include templates inside other templates. Recursive nesting is unsupported, as well as nesting too deeply (for performance reasons).

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
    <h1>{{ t: '{{ text }}' }}</h1>
</div>
```

We can reference 'theme' and 'text' when we instance the template like this:

```html
<esta-template template="heading" theme="dark" text="contact.title"></esta-template>
```

And the final result will be:

```html
<div class="heading dark">
    <h1>Contact</h1>
</div>
```

Where did the text 'Contact' came from? By using the next feature: translations.

### Translations

Multi-language support is handled by using translation files located in the 'lang' folder. You should make one JSON file for each language you want to support, named using a BCP 47 language subtag (like en, es, fr, etc). Use a key-based notation for your translations, like in the following example:

```json
{
    "key": "value",
    "hello": "Hello",
    "foo": {
        "bar": "bar",
    }
}
```

In order to access keys in templates and pages, use `{{ t: 'key' }}`, with `key` being a key from your translation files. Make sure all language files include all of the keys in use.

Example:

```html
`<h1>{{ t: 'foo.bar' }}</h1>`
```

Note: Translations are extremely barebores at the moment, with no support for plural forms, variations by context, or nesting. If you need advanced localisation features, it is recommended to use an external library or framework like [i18next](https://www.i18next.com/).

### Links

Internal links to any HTML document in your website can be resolved automatically.

Add links to internal pages using `{{ page: 'path' }}`, with `path` being the path to an HTML document in your 'pages' folder.

For example, `<a href="{{ page: 'blog/christmas.html' }}"></a>` will resolve as `<a href="https://mywebsite.com/en/blog/christmas.html"></a>` (in this case, the visitor is accessing the website in English).

Important: You must set a 'base_url' in your config file for this to work.

If you want to specify a language instead of automatically using the current one, add a 'lang' parameter:

`{{ page: 'path' lang: 'key' }}`

This is useful for implementing language selectors, for example.

### Assets

Link assets (images, video, fonts, server-side code, etc) using `{{ asset: 'path' }}`, with `path` being the relative path to a resource located in your 'assets' folder.

Example:

```html
<img src="{{ asset: 'img/sample.jpg' }}">`
```

Note: Esta manages browser-caching for assets, CSS, and JS files by keeping track of file modifications and adding hashes to filenames when building.

### CSS

Store CSS files 'css' directory you defined in the config file. Esta will automatically bundle them all into a single file when building, improving performance by reducing the number of requests.

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

GNU GENERAL PUBLIC LICENSE Version 3: [LICENSE](/LICENSE).
